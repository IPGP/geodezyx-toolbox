#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@author: psakic

This sub-module of geodezyx.files_rw contains functions to 
read RINEX files observation files.

it can be imported directly with:
from geodezyx import files_rw

The GeodeZYX Toolbox is a software for simple but useful
functions for Geodesy and Geophysics under the GNU GPL v3 License

Copyright (C) 2019 Pierre Sakic et al. (GFZ, pierre.sakic@gfz-postdam.de)
GitHub repository :
https://github.com/GeodeZYX/GeodeZYX-Toolbox_v4
"""

########## BEGIN IMPORT ##########
#### External modules
import numpy as np
import pandas as pd
from io import StringIO
import re
import os
from tqdm import tqdm

#### geodeZYX modules
from geodezyx import operational


#### Import the logger
import logging
log = logging.getLogger(__name__)


def read_rinex2_obs(rnx_in,
                    set_index=None):
    """
    Read a RINEX Observation, version 2 

    Parameters
    ----------
    rnx_in : str
        path of the input RINEX.
    set_index : str or list of str, optional
        define the columns for the index.
        If None, the output DataFrame is "flat", with integer index
        ["epoch","prn"] for instance set the epoch and the prn as MultiIndex
        The default is None.

    Returns
    -------
    DFrnxobs : Pandas DataFrame
    """
    
    
    EPOCHS = operational.rinex_read_epoch(rnx_in,out_index=True)
    FILE = open(rnx_in)
    LINES = FILE.readlines()
    
    #### Split header and Observation body
    for il,l in enumerate(LINES):
        if "END OF HEADER" in l:
            i_end_header = il
            break
        
    LINES_header = LINES[:i_end_header+1]
    
    #### get the observables
    Lines_obs = [l for l in LINES_header if '# / TYPES OF OBSERV' in l]
    ## clean SYS / # / OBS TYPES
    Lines_obs = [l[:60] for l in Lines_obs]
    
    ObsAllList_raw = " ".join(Lines_obs).split()
    ObsAllList = ObsAllList_raw[1:]
    ObsAllList = sorted([e for sublist in [(e,e+"_LLI",e+"_SSI") for e in ObsAllList] for e in sublist])
    
    nobs = int(ObsAllList_raw[0])
    nlines_for_obs = int(np.ceil(nobs/5)) ## 5 is the man num of obs in the RIENX specs
    
    
    DFall_stk = []
    
    #### reading the epochs    
    for iepoc in tqdm(range(len(EPOCHS)),desc="Reading " + os.path.basename(rnx_in)):
        epoch = EPOCHS[iepoc,0]
        ## define the start/end indices of the epoch block
        iline_start = EPOCHS[iepoc,1] 
        if iepoc == len(EPOCHS)-1:
            iline_end = None
        else:
            iline_end = EPOCHS[iepoc+1,1]
    
        ### get the lines of the epoch block
        Lines_epoc = LINES[iline_start:iline_end]
        
        ### get the satellites for this epoch block
        epoc,nsat,lineconcat,Sats_split,iline_sats_end = _sats_find(Lines_epoc)
        
        ### for each sat, merge the breaked lines
        Lines_obs = Lines_epoc[iline_sats_end+1:iline_end]
        Lines_obs = [e.replace("\n","") for e in Lines_obs]
        Lines_obs_merg = [Lines_obs[nlines_for_obs*n:nlines_for_obs*n+nlines_for_obs] for n in range(nsat)]
        Lines_obs_merg = ["".join(e) for e in Lines_obs_merg]
        
        ## read the epoch block using pandas' fixed width reader 
        B = StringIO("\n".join(Lines_obs_merg))
        columns_width = nobs*[14,1,1]
        DFepoch = pd.read_fwf(B,header=None,widths=columns_width)  
        DFepoch.columns = ObsAllList
        DFepoch["prn"] = Sats_split
        DFepoch["sys"] = DFepoch["prn"].str[0]
        DFepoch["epoch"] = epoch
        
        DFall_stk.append(DFepoch)
        
    
    ## final concat and cosmetic (reorder columns, sort)
    DFrnxobs = pd.concat(DFall_stk)
    DFrnxobs = DFrnxobs.reindex(["epoch","sys","prn"] + ObsAllList,axis=1)
    DFrnxobs.sort_values(["epoch","prn"],inplace=True)
    DFrnxobs.reset_index(drop=True,inplace=True)
    
    
    if set_index:
        DFrnxobs.set_index(set_index,inplace=True)
        DFrnxobs.sort_index(inplace=True)
        
    return DFrnxobs
        

def read_rinex3_obs(rnx_in,
                    set_index=None):
    """
    Read a RINEX Observation, version 3 or 4

    Parameters
    ----------
    rnx_in : str
        path of the input RINEX.
    set_index : str or list of str, optional
        define the columns for the index.
        If None, the output DataFrame is "flat", with integer index
        ["epoch","prn"] for instance set the epoch and the prn as MultiIndex
        The default is None.

    Returns
    -------
    DFrnxobs : Pandas DataFrame
    """
    
    EPOCHS = operational.rinex_read_epoch(rnx_in,out_index=True)
    FILE = open(rnx_in)
    LINES = FILE.readlines()
    
    #### Split header and Observation body
    for il,l in enumerate(LINES):
        if "END OF HEADER" in l:
            i_end_header = il
            break
        
    LINES_header = LINES[:i_end_header+1]
    #LINES_obs = LINES[i_end_header:]
    
    #### get the systems and observations
    Lines_sys = [l for l in LINES_header if 'SYS / # / OBS TYPES' in l]
    ## clean SYS / # / OBS TYPES
    Lines_sys = [l[:60] for l in Lines_sys]
    
    
    ## manage the 2 lines systems
    for il,l in enumerate(Lines_sys):
        if l[0] == " ":
            Lines_sys[il-1] = Lines_sys[il-1] + l
            Lines_sys.remove(l)
    
    #### store system and observables in a dictionnary
    dict_sys = dict()
    dict_sys_nobs = dict()
    dict_sys_use = dict() # adds the prn, and LLI and SSI indicators
    
    for il,l in enumerate(Lines_sys):
        Sysobs = l.split()
        dict_sys[Sysobs[0]] = Sysobs[2:]
        dict_sys_nobs[Sysobs[0]] = int(Sysobs[1])
        ## adds the LLI and SSI indicators
        dict_sys_use[Sysobs[0]] = [("prn",)] + [(e,e+"_LLI",e+"_SSI") for e in Sysobs[2:]]
        dict_sys_use[Sysobs[0]] = [e for sublist in dict_sys_use[Sysobs[0]] for e in sublist]
        
        if len(Sysobs[2:]) != int(Sysobs[1]):
            print("WARN: not the same length for XXXXXXXXXXX")
    
    ## the max number of observable (for the reading)
    ##ObsAllList = list(sorted(set([e for sublist in list(dict_sys_use.values())[1:] for e in sublist]))) 
    nobs_max = max(dict_sys_nobs.values())
    
    DFall_stk = []
    #### reading the epochs
    for iepoc in tqdm(range(len(EPOCHS)),desc="Reading " + os.path.basename(rnx_in)):
        epoch = EPOCHS[iepoc,0]
        ## define the start/end indices of the epoch block
        iline_start = EPOCHS[iepoc,1] + 1
        if iepoc == len(EPOCHS)-1:
            iline_end = None
        else:
            iline_end = EPOCHS[iepoc+1,1]
        
        Lines_epoc = LINES[iline_start:iline_end]
        
        ## read the epoch block using pandas' fixed width reader 
        B = StringIO("".join(Lines_epoc))
        columns_width = [3] + nobs_max*[14,1,1]
        DFepoch = pd.read_fwf(B,header=None,widths=columns_width)      
        
        DFepoch_ok_stk = []
        #### assign the correct observable names for each system
        for sys in dict_sys_use.keys():
            #DFepoch_sys = DFepoch[DFepoch[0].str[0] == sys]
            #                   get the sats of the system sys  ||  get the meaningful columns
            DFepoch_sys_clean = DFepoch[DFepoch[0].str[0] == sys].iloc[:,:len(dict_sys_use[sys])]
            DFepoch_sys_clean.columns = dict_sys_use[sys]
            DFepoch_ok_stk.append(DFepoch_sys_clean)
                        
        DFepoch_ok = pd.concat(DFepoch_ok_stk)
        # An epoch column is created to fasten the process
        col_epoch = pd.Series([epoch]*len(DFepoch_ok),name="epoch")
        col_sys = pd.Series(DFepoch_ok['prn'].str[0],name="sys")
        DFepoch_ok = pd.concat([col_epoch,col_sys,DFepoch_ok],axis=1)
                
        DFall_stk.append(DFepoch_ok)
    
    ## final concat and cosmetic (reorder columns, sort)
    DFrnxobs = pd.concat(DFall_stk)
    #Col_names = list(DFrnxobs.columns)
    #Col_names.remove("epoch")
    #Col_names.remove("prn")
    #Col_names = ["epoch","prn"] + sorted(Col_names)
    #DFrnxobs = DFrnxobs.reindex(Col_names,axis=1)
    
    DFrnxobs.reset_index(drop=True,inplace=True)   
    
    if set_index:
        DFrnxobs.set_index(set_index,inplace=True)
        DFrnxobs.sort_index(inplace=True)
        
    return DFrnxobs


############ INTERNAL FUNCTIONS


def _sats_find(Lines_inp):
    """
    For RINEX2 only
    search for the satellites for each epoch block by reading the 
    EPOCH/SAT record

    Parameters
    ----------
    Lines_inp : List of str
        the lines of one epoch block (EPOCH/SAT + OBSERVATION records).

    Returns
    -------
    bloc_tuple : tuple
        a 5-tuple containing:
            epoc : datetime, the epoch of block
            nsat : int, the number of satellites
            lineconcat : str, the satellites as a concatenated string  
            Sats_split : list of str, the satellites as a list
            il : int, the index of the last line of the EPOCH/SAT record

    """
    iline_bloc = 0
    nlines_bloc = -1
    for il,l in enumerate(Lines_inp):
        ##### 
        re_epoch = '^ {1,2}([0-9]{1,2} * ){5}'
        #re_sat="[A-Z][0-9][0-9]"
        bool_epoch=re.search(re_epoch,l)
        #bool_sat=re.search(re_sat,l)
        
        ### we found an epoch line
        if bool_epoch:
            in_epoch = True
            nsat = int(l[30:32])
            iline_bloc = 0
            nlines_bloc = int(np.ceil(nsat / 12))
            LineBloc = []
            lineconcat = ""
            epoc = operational.read_rnx_epoch_line(l,rnx2=True)
        
        ### we read the sat lines based on the number of sat
        if iline_bloc <= nlines_bloc:
            LineBloc.append(l[32:].strip())
            lineconcat = lineconcat + l[32:].strip()
            iline_bloc += 1
        
        ### we stack everything when the sat block is over
        if iline_bloc == nlines_bloc:
            in_epoch = False
            Sats_split = [lineconcat[3*n:3*n+3] for n in range(nsat)]
            bloc_tuple = (epoc,nsat,lineconcat,Sats_split,il)
            return bloc_tuple



def _line_reader(linein,nobs):
    """
    DISCONTINUED
    
    For RINEX3 Only 
    
    read the content of an observation line. pd.read_fwf does the job
    """
    columns_width = [3] + nobs*[14,1,1]
    columns_cumul = [0] + list(np.cumsum(columns_width))
    
    out_stk = []
    for i in range(len(columns_cumul)-1):
        slic = slice(columns_cumul[i],columns_cumul[i+1])
        out = linein[slic]
        if i == 0:
            out_stk.append(out)
        else:
            try:
                out_stk.append(float(out))
            except:
                out_stk.append(np.nan)
    
    return out_stk