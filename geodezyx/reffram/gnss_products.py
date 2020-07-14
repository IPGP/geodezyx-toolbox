#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Aug  2 17:36:39 2019

@author: psakicki
"""

########## BEGIN IMPORT ##########
#### External modules
import matplotlib
import matplotlib.pyplot as plt
import natsort
import numpy as np
import os 
import pandas as pd
import re

#### geodeZYX modules
from geodezyx import conv
from geodezyx import files_rw
from geodezyx import stats
from geodezyx import utils

##########  END IMPORT  ##########

def compar_orbit(Data_inp_1,Data_inp_2,step_data = 900,
                 sats_used_list = ['G'],
                 name1='',name2='',use_name_1_2_for_table_name = False,
                 RTNoutput = True,convert_ECEF_ECI=True,
                 clean_null_values = True,
                 conv_coef=10**3,return_satNull = False):
    """
    Compares 2 GNSS orbits files (SP3), and gives a summary plot and a
    statistics table

    Parameters
    ----------
    Data_inp_1 & Data_inp_2 : str or Pandas DataFrame
        contains the orbits or path (string) to the sp3

    step_data : int
        per default data sampling

    sats_used_list : list of str
        used constellation or satellite : G E R C ... E01 , G02 ...
        Individuals satellites are prioritary on whole constellations
        e.g. ['G',"E04"]


    RTNoutput : bool
        select output, Radial Transverse Normal or XYZ

    convert_ECEF_ECI : bool
        convert sp3 ECEF => ECI, must be True in operational !

    name1 & name2 : str (optionals)
        optional custom names for the 2 orbits

    use_name_1_2_for_table_name : bool
        False : use name 1 and 2 for table name, use datafile instead

    clean_null_values : bool or str
        if True or "all" remove sat position in all X,Y,Z values
        are null (0.000000)
        if "any", remove sat position if X or Y or Z is null
        if False, keep everything
        
    conv_coef : int
        conversion coefficient, km to m 10**3, km to mm 10**6

    Returns
    -------
    Diff_sat_all : Pandas DataFrame
    contains differences b/w Data_inp_1 & Data_inp_2
    in Radial Transverse Normal OR XYZ frame

        Attributes of Diff_sat_all :
            Diff_sat_all.name : title of the table

    Note
    ----
    clean_null_values if useful (and necessary) only if
    convert_ECEF_ECI = False
    if convert_ECEF_ECI = True, the cleaning will be done by
    a side effect trick : the convertion ECEF => ECI will generate NaN
    for a zero-valued position
    But, nevertheless, activating  clean_null_values = True is better
    This Note is in fact usefull if you want to see bad positions on a plot
    => Then convert_ECEF_ECI = False and clean_null_values = False

    Source
    ------
    "Coordinate Systems", ASEN 3200 1/24/06 George H. Born

    """

    # selection of both used Constellations AND satellites
    const_used_list = []
    sv_used_list    = []
    for sat in sats_used_list:
        if len(sat) == 1:
            const_used_list.append(sat)
        elif len(sat) == 3:
            sv_used_list.append(sat)
            if not sat[0] in const_used_list:
                const_used_list.append(sat[0])

    # Read the files or DataFrames
    # metadata attributes are not copied
    # Thus, manual copy ...
    # (Dirty way, should be impoved without so many lines ...)
    if type(Data_inp_1) is str:
        D1orig = files_rw.read_sp3(Data_inp_1,epoch_as_pd_index=True)
    else:
        D1orig = Data_inp_1.copy(True)
        try:
            D1orig.name = Data_inp_1.name
        except:
            D1orig.name = "no_name"
        try:
            D1orig.path = Data_inp_1.path
        except:
            D1orig.path = "no_path"
        try:
            D1orig.filename = Data_inp_1.filename
        except:
            D1orig.filename = "no_filename"

    if type(Data_inp_2) is str:
        D2orig = files_rw.read_sp3(Data_inp_2,epoch_as_pd_index=True)
    else:
        D2orig = Data_inp_2.copy(True)
        try:
            D2orig.name = Data_inp_2.name
        except:
            D2orig.name = "no_name"
        try:
            D2orig.path = Data_inp_2.path
        except:
            D2orig.path = "no_path"
        try:
            D2orig.filename = Data_inp_2.filename
        except:
            D2orig.filename = "no_filename"

    #### NB : It has been decided with GM that the index of a SP3 dataframe
    ####      will be integers, not epoch datetime anymore
    ####      BUT here, for legacy reasons, the index has to be datetime

    if isinstance(D1orig.index[0], (int, np.integer)):
        D1orig.set_index("epoch",inplace=True)

    if isinstance(D2orig.index[0], (int, np.integer)):
        D2orig.set_index("epoch",inplace=True)

    Diff_sat_stk = []

    # This block is for removing null values
    if clean_null_values:
        if clean_null_values == "all":
            all_or_any = np.all
        elif clean_null_values == "any":
            all_or_any = np.any
        else:
            all_or_any = np.all

        xyz_lst = ['x','y','z']

        D1_null_bool = all_or_any(np.isclose(D1orig[xyz_lst],0.),axis=1)
        D2_null_bool = all_or_any(np.isclose(D2orig[xyz_lst],0.),axis=1)

        D1 = D1orig[np.logical_not(D1_null_bool)]
        D2 = D2orig[np.logical_not(D2_null_bool)]

        if np.any(D1_null_bool) or np.any(D2_null_bool):
            sat_nul = utils.join_improved(" " ,*list(set(D1orig[D1_null_bool]["sat"])))
            print("WARN : Null values contained in SP3 files : ")
            print("f1:" , np.sum(D1_null_bool) , utils.join_improved(" " ,
                  *list(set(D1orig[D1_null_bool]["sat"]))))
            print("f2:" , np.sum(D2_null_bool) , utils.join_improved(" " ,
                  *list(set(D2orig[D2_null_bool]["sat"]))))
        else:
            sat_nul = []

    else:
        D1 = D1orig.copy()
        D2 = D2orig.copy()

    for constuse in const_used_list:
        D1const = D1[D1['const'] == constuse]
        D2const = D2[D2['const'] == constuse]

        # checking if the data correspond to the step
        bool_step1 = np.mod((D1const.index - np.min(D1.index)).seconds,step_data) == 0
        bool_step2 = np.mod((D2const.index - np.min(D2.index)).seconds,step_data) == 0

        D1window = D1const[bool_step1]
        D2window = D2const[bool_step2]

        # find common sats and common epochs
        sv_set   = sorted(list(set(D1window['sv']).intersection(set(D2window['sv']))))
        epoc_set = sorted(list(set(D1window.index).intersection(set(D2window.index))))

        # if special selection of sats, then apply it
        # (it is late and this selection is incredibely complicated ...)
        if np.any([True  if constuse in e else False for e in sv_used_list]):
            # first find the selected sats for the good constellation
            sv_used_select_list = [int(e[1:]) for e in sv_used_list if constuse in e]
            #and apply it
            sv_set = sorted(list(set(sv_set).intersection(set(sv_used_select_list))))

        for svv in sv_set:
            # First research : find corresponding epoch for the SV
            # this one is sufficent if there is no gaps (e.g. with 0.00000) i.e.
            # same nb of obs in the 2 files
            # NB : .reindex() is smart, it fills the DataFrame
            # with NaN
            try:
                D1sv_orig = D1window[D1window['sv'] == svv].reindex(epoc_set)
                D2sv_orig = D2window[D2window['sv'] == svv].reindex(epoc_set)
            except Exception as exce:
                print("ERR : Unable to re-index with an unique epoch")
                print("      are you sure there is no multiple-defined epochs for the same sat ?")
                print("      it happens e.g. when multiple ACs are in the same DataFrame ")
                print("TIP : Filter the input Dataframe before calling this fct with")
                print("      DF = DF[DF['AC'] == 'gbm']")
                
                Dtmp1 = D1orig[D1orig['sv'] == svv]
                Dtmp2 = D2orig[D2orig['sv'] == svv]
                
                dupli1 = np.sum(Dtmp1.duplicated(["epoch","sat"]))
                dupli2 = np.sum(Dtmp2.duplicated(["epoch","sat"]))
                
                print("FWIW : duplicated epoch/sat in DF1 & DF2 : ",dupli1,dupli2)

                raise exce

            # Second research, it is a security in case of gap
            # This step is useless, because .reindex() will fill the DataFrame
            # with NaN
            if len(D1sv_orig) != len(D2sv_orig):
                print("INFO : different epochs nbr for SV",svv,len(D1sv_orig),len(D2sv_orig))
                epoc_sv_set = sorted(list(set(D1sv_orig.index).intersection(set(D2sv_orig.index))))
                D1sv = D1sv_orig.loc[epoc_sv_set]
                D2sv = D2sv_orig.loc[epoc_sv_set]
            else:
                D1sv = D1sv_orig
                D2sv = D2sv_orig

            P1     = D1sv[['x','y','z']]
            P2     = D2sv[['x','y','z']]

            # Start ECEF => ECI
            if convert_ECEF_ECI:
                # Backup because the columns xyz will be reaffected
                #D1sv_bkp = D1sv.copy()
                #D2sv_bkp = D2sv.copy()
    
                P1b = conv.ECEF2ECI(np.array(P1),conv.dt_gpstime2dt_utc(P1.index.to_pydatetime(),out_array=True))
                P2b = conv.ECEF2ECI(np.array(P2),conv.dt_gpstime2dt_utc(P2.index.to_pydatetime(),out_array=True))

                D1sv[['x','y','z']] = P1b
                D2sv[['x','y','z']] = P2b

                P1  = D1sv[['x','y','z']]
                P2  = D2sv[['x','y','z']]
            # End ECEF => ECI

            if not RTNoutput:
                # Compatible with the documentation +
                # empirically tested with OV software
                # it is  P1 - P2 (and not P2 - P1)
                Delta_P = P1 - P2


                Diff_sat = Delta_P.copy()
                Diff_sat.columns = ['dx','dy','dz']

            else:
                rnorm = np.linalg.norm(P1,axis=1)

                Vx = utils.diff_pandas(D1sv,'x')
                Vy = utils.diff_pandas(D1sv,'y')
                Vz = utils.diff_pandas(D1sv,'z')

                V =  pd.concat((Vx , Vy , Vz),axis=1)
                V.columns = ['vx','vy','vz']

                R = P1.divide(rnorm,axis=0)
                R.columns = ['xnorm','ynorm','znorm']

                H      = pd.DataFrame(np.cross(R,V),columns=['hx','hy','hz'])
                hnorm  = np.linalg.norm(H,axis=1)

                C         = H.divide(hnorm,axis=0)
                C.columns = ['hxnorm','hynorm','hznorm']

                I         = pd.DataFrame(np.cross(C,R),columns=['ix','iy','iz'])

                R_ar = np.array(R)
                I_ar = np.array(I)
                C_ar = np.array(C)

                #R_ar[1]
                Beta = np.stack((R_ar,I_ar,C_ar),axis=1)

                # Compatible with the documentation +
                # empirically tested with OV software
                # it is  P1 - P2 (and not P2 - P1)
                Delta_P = P1 - P2

                # Final determination
                Astk = []

                for i in range(len(Delta_P)):
                    A = np.dot(Beta[i,:,:],np.array(Delta_P)[i])
                    Astk.append(A)

                Diff_sat = pd.DataFrame(np.vstack(Astk),
                                   index = P1.index,columns=['dr','dt','dn'])

            Diff_sat = Diff_sat * conv_coef # metrer conversion

            Diff_sat['const'] = [constuse] * len(Diff_sat.index)
            Diff_sat['sv']    = [svv]      * len(Diff_sat.index)
            Diff_sat['sat']   = [constuse + str(svv).zfill(2)] * len(Diff_sat.index)

            Diff_sat_stk.append(Diff_sat)

    Diff_sat_all = pd.concat(Diff_sat_stk)
    Date = Diff_sat.index[0]

    # Attribute definition
    if RTNoutput:
        Diff_sat_all.frame_type = 'RTN'

        # Pandas donesn't manage well iterable as attribute
        # So, it is separated
        Diff_sat_all.frame_col_name1 = 'dr'
        Diff_sat_all.frame_col_name2 = 'dt'
        Diff_sat_all.frame_col_name3 = 'dn'

    else:
        # Pandas donesn't manage well iterable as attribute
        # So, it is separated
        Diff_sat_all.frame_col_name1 = 'dx'
        Diff_sat_all.frame_col_name2 = 'dy'
        Diff_sat_all.frame_col_name3 = 'dz'

        if convert_ECEF_ECI:
            Diff_sat_all.frame_type = 'ECI'
        else:
            Diff_sat_all.frame_type = 'ECEF'


    # Name definitions
    if name1:
        Diff_sat_all.name1 = name1
    else:
        Diff_sat_all.name1 = D1orig.name

    if name2:
        Diff_sat_all.name2 = name2
    else:
        Diff_sat_all.name2 = D2orig.name

    Diff_sat_all.filename1 = D1orig.filename
    Diff_sat_all.filename2 = D2orig.filename

    Diff_sat_all.path1 = D1orig.path
    Diff_sat_all.path2 = D2orig.path

    Diff_sat_all.name = ' '.join(('Orbits comparison ('+Diff_sat_all.frame_type +') b/w',
                                  Diff_sat_all.name1 ,'(ref.) and',
                                  Diff_sat_all.name2 ,',',Date.strftime("%Y-%m-%d"),
                                  ', doy', str(conv.dt2doy(Date))))

    
    if return_satNull:
        return Diff_sat_all, sat_nul
    else:
        return Diff_sat_all


def compar_orbit_plot(Diff_sat_all_df_in,
                      save_plot=False,
                      save_plot_dir="",
                      save_plot_name="auto",
                      save_plot_name_suffix=None,
                      save_plot_ext=(".pdf",".png",".svg"),
                      yaxis_limit=None):
    """
    General description

    Parameters
    ----------
    Diff_sat_all_df_in : DataFrame
        a DataFrame produced by compar_orbit
        
    yaxis_limit : 3-tuple iterable
        force the y axis limits. must look like 
        [(ymin_r,ymax_r),(ymin_t,ymax_t),(ymin_n,ymax_n)]

    Returns
    -------
    the Figure and the 3 Axes if no save is asked
    export path (str) if save is asked
    but plot a plot anyway
    """

    import matplotlib.dates as mdates
    fig,[axr,axt,axn] = plt.subplots(3,1,sharex='all')

    satdispo = natsort.natsorted(list(set(Diff_sat_all_df_in['sat'])))

    SymbStk = []

    cm = plt.get_cmap('viridis')
    NUM_COLORS = len(satdispo)
    Colors = [cm(1.*i/NUM_COLORS) for i in range(NUM_COLORS)]

    # Pandas donesn't manage well iterable as attribute
    # So, it is separated
    try:
        col_name0 = Diff_sat_all_df_in.frame_col_name1
        col_name1 = Diff_sat_all_df_in.frame_col_name2
        col_name2 = Diff_sat_all_df_in.frame_col_name3
    except:
        col_name0 = Diff_sat_all_df_in.columns[0]
        col_name1 = Diff_sat_all_df_in.columns[1]
        col_name2 = Diff_sat_all_df_in.columns[2]

    for satuse,color in zip(satdispo,Colors):
        Diffuse = Diff_sat_all_df_in[Diff_sat_all_df_in['sat'] == satuse]

        Time = Diffuse.index
        R    = Diffuse[col_name0]
        T    = Diffuse[col_name1]
        N    = Diffuse[col_name2]

        #fig.fmt_xdata = mdates.DateFormatter('%Y-%m-%d')

        Symb = axr.plot(Time,R,label=satuse,c=color)
        axt.plot(Time,T,label=satuse,c=color)
        axn.plot(Time,N,label=satuse,c=color)

        SymbStk.append(Symb[0])

        fig.autofmt_xdate()

    if Diff_sat_all_df_in.frame_type == 'RTN':
        axr.set_ylabel('Radial diff. (m)')
        axt.set_ylabel('Transverse diff. (m)')
        axn.set_ylabel('Normal diff. (m)')

    else:
        axr.set_ylabel(Diff_sat_all_df_in.frame_type + ' X diff. (m)')
        axt.set_ylabel(Diff_sat_all_df_in.frame_type + ' Y diff. (m)')
        axn.set_ylabel(Diff_sat_all_df_in.frame_type + ' Z diff. (m)')


    y_formatter = matplotlib.ticker.ScalarFormatter(useOffset=False)
    axr.yaxis.set_major_formatter(y_formatter)
    axt.yaxis.set_major_formatter(y_formatter)
    axn.yaxis.set_major_formatter(y_formatter)
    
    if yaxis_limit:
        axr.set_ylim(yaxis_limit[0])
        axt.set_ylim(yaxis_limit[1])
        axn.set_ylim(yaxis_limit[2])
    
    import matplotlib.dates as mdates
    fig.fmt_xdata = mdates.DateFormatter('%Y-%m-%d')

    lgd = fig.legend(tuple(SymbStk), satdispo , loc='lower center',ncol=8,
                     columnspacing=1)

    fig.set_size_inches(8.27,11.69)
    plt.suptitle(Diff_sat_all_df_in.name)
    plt.tight_layout()
    plt.subplots_adjust(top=0.95)
    plt.subplots_adjust(bottom=0.15)

    if save_plot:
        if save_plot_name == "auto":
            save_plot_name = "_".join((Diff_sat_all_df_in.name1,
                                      Diff_sat_all_df_in.name2,
                                      Diff_sat_all_df_in.index.min().strftime("%Y-%m-%d")))
            
        if save_plot_name_suffix:
            save_plot_name = save_plot_name + '_' + save_plot_name_suffix

        for ext in save_plot_ext:
            save_plot_path = os.path.join(save_plot_dir,save_plot_name)
            plt.savefig(save_plot_path + ext)
            return_val = save_plot_path
            
    else:
        return_val = fig,(axr,axt,axn)

    return return_val

def compar_orbit_table(Diff_sat_all_df_in,RMS_style = 'natural',
                       light_tab  = False):
    """
    Generate a table with statistical indicators for an orbit comparison
    (RMS mean, standard dev, ...)
    Parameters
    ----------
    Diff_sat_all_df_in : Pandas DataFrame
        a DataFrame produced by compar_orbit

    RMS_style : str
        'natural': use the natural definition of the RMS
        'GRGS': RMS calc based on the GRGS definition of the RMS (OV help)
                is actually the standard deviation
        'kouba': RMS as defined in Kouba et al. 1994, p75
                 using the degree of freedom (3*Nobs - 7)

    light_tab : bool
        produce a table with only RMS, with min/max/arithmetic instead

    Returns
    -------
    Compar_tab_out : DataFrame
        Statistical results of the comparison

    Note
    ----
    you can pretty print the output DataFrame using tabular module
    here is a template:

    >>> from tabulate import tabulate
    >>> print(tabulate(ComparTable,headers="keys",floatfmt=".4f"))
    """

    sat_list = utils.uniq_and_sort(Diff_sat_all_df_in['sat'])

    # Pandas donesn't manage well iterable as attribute
    # So, it is separated
    try:
        col_name0 = Diff_sat_all_df_in.frame_col_name1
        col_name1 = Diff_sat_all_df_in.frame_col_name2
        col_name2 = Diff_sat_all_df_in.frame_col_name3
    except:
        col_name0 = Diff_sat_all_df_in.columns[0]
        col_name1 = Diff_sat_all_df_in.columns[1]
        col_name2 = Diff_sat_all_df_in.columns[2]

    rms_stk = []

    for sat in sat_list:
        Diffwork = utils.df_sel_val_in_col(Diff_sat_all_df_in,'sat',sat)

        if RMS_style == "natural":
            rms_A = stats.rms_mean(Diffwork[col_name0])
            rms_B = stats.rms_mean(Diffwork[col_name1])
            rms_C = stats.rms_mean(Diffwork[col_name2])
        elif RMS_style == "GRGS":
            rms_A = stats.rms_mean(Diffwork[col_name0] - Diffwork[col_name0].mean())
            rms_B = stats.rms_mean(Diffwork[col_name1] - Diffwork[col_name1].mean())
            rms_C = stats.rms_mean(Diffwork[col_name2] - Diffwork[col_name2].mean())
        elif RMS_style == "kouba":
            rms_A = stats.rms_mean_kouba(Diffwork[col_name0])
            rms_B = stats.rms_mean_kouba(Diffwork[col_name1])
            rms_C = stats.rms_mean_kouba(Diffwork[col_name2])

            
            
            
        RMS3D = np.sqrt(rms_A**2 + rms_B**2 + rms_C**2)

        min_A = Diffwork[col_name0].min()
        min_B = Diffwork[col_name1].min()
        min_C = Diffwork[col_name2].min()

        max_A = Diffwork[col_name0].max()
        max_B = Diffwork[col_name1].max()
        max_C = Diffwork[col_name2].max()

        mean_A = Diffwork[col_name0].mean()
        mean_B = Diffwork[col_name1].mean()
        mean_C = Diffwork[col_name2].mean()

        if light_tab:
            rms_stk.append([rms_A,rms_B,rms_C,RMS3D])
        else:
            rms_stk.append([rms_A,rms_B,rms_C,RMS3D,
                            min_A,max_A,mean_A,
                            min_B,max_B,mean_B,
                            min_C,max_C,mean_C])


    #################################
             # ALL SATS
    if RMS_style == "natural":
        rms_A = stats.rms_mean(Diff_sat_all_df_in[col_name0])
        rms_B = stats.rms_mean(Diff_sat_all_df_in[col_name1])
        rms_C = stats.rms_mean(Diff_sat_all_df_in[col_name2])
        RMS3D = np.sqrt(rms_A**2 + rms_B**2 + rms_C**2)
    elif RMS_style == "GRGS":
        rms_A = stats.rms_mean(Diff_sat_all_df_in[col_name0] - Diff_sat_all_df_in[col_name0].mean())
        rms_B = stats.rms_mean(Diff_sat_all_df_in[col_name1] - Diff_sat_all_df_in[col_name1].mean())
        rms_C = stats.rms_mean(Diff_sat_all_df_in[col_name2] - Diff_sat_all_df_in[col_name2].mean())
        RMS3D = np.sqrt(rms_A**2 + rms_B**2 + rms_C**2)
    elif RMS_style == "kouba":
        rms_A = stats.rms_mean_kouba(Diff_sat_all_df_in[col_name0])
        rms_B = stats.rms_mean_kouba(Diff_sat_all_df_in[col_name1])
        rms_C = stats.rms_mean_kouba(Diff_sat_all_df_in[col_name2])
        RMS3D = np.sqrt(rms_A**2 + rms_B**2 + rms_C**2)


    min_A = Diff_sat_all_df_in[col_name0].min()
    min_B = Diff_sat_all_df_in[col_name1].min()
    min_C = Diff_sat_all_df_in[col_name2].min()

    max_A = Diff_sat_all_df_in[col_name0].max()
    max_B = Diff_sat_all_df_in[col_name1].max()
    max_C = Diff_sat_all_df_in[col_name2].max()

    mean_A = Diff_sat_all_df_in[col_name0].mean()
    mean_B = Diff_sat_all_df_in[col_name1].mean()
    mean_C = Diff_sat_all_df_in[col_name2].mean()

    if light_tab:
        rms_stk.append([rms_A,rms_B,rms_C,RMS3D])
    else:
        rms_stk.append([rms_A,rms_B,rms_C,RMS3D,
                        min_A,max_A,mean_A,
                        min_B,max_B,mean_B,
                        min_C,max_C,mean_C])

             # ALL SATS
    #################################

    if  Diff_sat_all_df_in.frame_type == 'RTN':
        if light_tab:
            cols_nam = ["rmsR","rmsT","rmsN","rms3D"]
        else:
            cols_nam = ["rmsR","rmsT","rmsN","rms3D",
                        "minR","maxR","meanR",
                        "minT","maxT","meanT",
                        "minN","maxN","meanN"]

    else:
        if light_tab:
            cols_nam = ["rmsX","rmsY","rmsZ","rms3D"]
        else:
            cols_nam = ["rmsX","rmsY","rmsZ","rms3D",
                        "minX","maxX","meanX",
                        "minY","maxY","meanY",
                        "minZ","maxZ","meanZ"]

    Compar_tab_out     = pd.DataFrame(rms_stk,index=sat_list + ['ALL'],
                                      columns=cols_nam)

    return Compar_tab_out


def compar_orbit_frontend(DataDF1,DataDF2,ac1,ac2, sats_used_list = ['G']):
    K = compar_orbit(DataDF1[DataDF1["AC"] == ac1],
                     DataDF2[DataDF2["AC"] == ac2],
                     sats_used_list=sats_used_list)
    compar_orbit_plot(K)
    return K


def compar_sinex(snx1 , snx2 , stat_select = None, invert_select=False,
                 out_means_summary=True,out_meta=True,out_dataframe = True,
                 manu_wwwwd=None):

    if type(snx1) is str:
        week1 = utils.split_improved(os.path.basename(snx1),"_",".")[:]
        week2 = utils.split_improved(os.path.basename(snx2),"_",".")[:]
        if week1 != week2:
            print("WARN : Dates of 2 input files are differents !!! It might be very bad !!!",week1,week2)
        else:
            wwwwd = week1
        D1 = files_rw.read_sinex(snx1,True)
        D2 = files_rw.read_sinex(snx2,True)
    else:
        print("WARN : you are giving the SINEX input as a DataFrame, wwwwd has to be given manually using manu_wwwwd")
        D1 = snx1
        D2 = snx2


    if manu_wwwwd:
        wwwwd = manu_wwwwd


    STATCommon  = set(D1["STAT"]).intersection(set(D2["STAT"]))

    if stat_select:

        STATCommon_init = list(STATCommon)

        if invert_select:
            select_fct = lambda x : not x
        else:
            select_fct = lambda x : x

        if type(stat_select) is str:
            STATCommon = [sta for sta in STATCommon_init if select_fct(re.search(stat_select, sta)) ]
        elif utils.is_iterable(stat_select):
            STATCommon = [sta for sta in STATCommon_init if select_fct(sta in stat_select) ]
        else:
            print("WARN : check type of stat_select")

    D1Common = D1[D1["STAT"].isin(STATCommon)].sort_values("STAT").reset_index(drop=True)
    D2Common = D2[D2["STAT"].isin(STATCommon)].sort_values("STAT").reset_index(drop=True)


    Ddiff = pd.DataFrame()
    Ddiff = Ddiff.assign(STAT=D1Common["STAT"])

    #### XYZ Part
    for xyz in ("x","y","z"):

        dif = pd.to_numeric((D2Common[xyz] - D1Common[xyz]))

        Ddiff = Ddiff.assign(xyz=dif)
        Ddiff = Ddiff.rename(columns={"xyz": xyz})

    D3D = np.sqrt((Ddiff["x"]**2 + Ddiff["y"]**2 + Ddiff["z"]**2 ).astype('float64'))

    Ddiff = Ddiff.assign(d3D_xyz=D3D)

    ### ENU Part
    E , N ,U = [] , [] , []
    enu_stk = []

    for (_,l1) , (_,l2) in zip( D1Common.iterrows() , D2Common.iterrows() ):
        enu   = conv.XYZ2ENU_2(l1["x"],l1["y"],l1["z"],l2["x"],l2["y"],l2["z"])
        enu_stk.append(np.array(enu))


    if len(enu_stk) == 0:
        E,N,U = np.array([]) , np.array([]) , np.array([])
    else:
        ENU = np.hstack(enu_stk)
        E,N,U = ENU[0,:] , ENU[1,:] , ENU[2,:]


    D2D = np.sqrt((E**2 + N**2).astype('float64'))
    D3D = np.sqrt((E**2 + N**2 + U**2 ).astype('float64'))

    Ddiff = Ddiff.assign(e=E)
    Ddiff = Ddiff.assign(n=N)
    Ddiff = Ddiff.assign(u=U)
    Ddiff = Ddiff.assign(d2D_enu=D2D)
    Ddiff = Ddiff.assign(d3D_enu=D3D)

    #    E,N,U    = conv.XYZ2ENU_2((X,Y,Z,x0,y0,z0))
    #    E,N,U    = conv.XYZ2ENU_2((X,Y,Z,x0,y0,z0))

    if out_dataframe:
        out_meta = True


    if not out_means_summary:
        print("INFO : this is not used operationally and it can be improved")
        return Ddiff
    else:
        output = []

        col_names = ("x","y","z","d3D_xyz",
                     "e","n","u","d2D_enu","d3D_enu")

        for xyz in col_names:
            output.append(stats.rms_mean(Ddiff[xyz]))
        for xyz in col_names:
            output.append(np.nanmean(Ddiff[xyz]))
        for xyz in col_names:
            output.append(np.nanstd(Ddiff[xyz]))

        if out_meta:
            print(wwwwd)
            nstat = len(STATCommon)
            week   = int(wwwwd[:4])
            day    = int(wwwwd[4:])
            output = [week , day ,nstat] + output


        if not out_dataframe:
            return tuple(output)
        else:

            output_DF = pd.DataFrame(output).transpose()

            output_DF.columns = ["week","dow","nbstat",
             "x_rms","y_rms","z_rms","d3D_xyz_rms",
             "e_rms","n_rms","u_rms","d2D_enu_rms","d3D_enu_rms",
             "x_ari","y_ari","z_ari","d3D_xyz_ari",
             "e_ari","n_ari","u_ari","d2D_enu_ari","d3D_enu_ari",
             "x_ari","y_std","z_std","d3D_xyz_std",
             "e_ari","n_std","u_std","d2D_enu_std","d3D_enu_std"]

            return output_DF


#   ____       _     _ _     _____        _        ______                             
#  / __ \     | |   (_) |   |  __ \      | |      |  ____|                            
# | |  | |_ __| |__  _| |_  | |  | | __ _| |_ __ _| |__ _ __ __ _ _ __ ___   ___  ___ 
# | |  | | '__| '_ \| | __| | |  | |/ _` | __/ _` |  __| '__/ _` | '_ ` _ \ / _ \/ __|
# | |__| | |  | |_) | | |_  | |__| | (_| | || (_| | |  | | | (_| | | | | | |  __/\__ \
#  \____/|_|  |_.__/|_|\__| |_____/ \__,_|\__\__,_|_|  |_|  \__,_|_| |_| |_|\___||___/
#                                                                                     
       
### Orbit DataFrames                                                                      

#### FCT DEF
def OrbDF_reg_2_multidx(OrbDFin,index_order=["sat","epoch"]):
    """
    From an regular Orbit DF generated by read_sp3(), set some columns 
    (typically ["sat","epoch"]) as indexes
    The outputed DF is then a Multi-index DF
    """
    OrbDFwrk = OrbDFin.reset_index()
    OrbDFwrk = OrbDFwrk.sort_values(index_order)
    OrbDFwrk = OrbDFwrk.set_index(index_order,inplace=False)
    return OrbDFwrk

def OrbDF_multidx_2_reg(OrbDFin,index_order=["sat","epoch"]):
    """
    Convert a Multi-index formatted OrbitDF to his original form
    """
    OrbDFwrk = OrbDFin.reset_index()
    OrbDFwrk = OrbDFwrk.sort_values(index_order)
    OrbDFwrk["const"] = OrbDFwrk["sat"].apply(lambda x: x[0])
    OrbDFwrk["sv"]    = OrbDFwrk["sat"].apply(lambda x: int(x[1:]))
    return OrbDFwrk

def OrbDF_common_epoch_finder(OrbDFa_in,OrbDFb_in,return_index=False,
                              supplementary_sort=True):
    """
    Find common sats and epochs in to Orbit DF, and output the
    corresponding Orbit DFs
    """
    OrbDFa = OrbDF_reg_2_multidx(OrbDFa_in)
    OrbDFb = OrbDF_reg_2_multidx(OrbDFb_in)
    
    I1 = OrbDFa.index
    I2 = OrbDFb.index
    
    Iinter = I1.intersection(I2)
    ### A sort of the Index to avoid issues ...
    Iinter = Iinter.sort_values()
    
    OrbDFa_out = OrbDFa.loc[Iinter]
    OrbDFb_out = OrbDFb.loc[Iinter]
    
    if supplementary_sort:
        # for multi GNSS, OrbDF_out are not well sorted (why ??? ...)
        # we do a supplementary sort
        # NB 202003: maybe because Iiter was not sorted ...
        # should be fixed with the Iinter.sort_values() above 
        # but we maintain this sort
        OrbDFa_out = OrbDFa_out.sort_values(["sat","epoch"])
        OrbDFb_out = OrbDFb_out.sort_values(["sat","epoch"])

    
    if len(OrbDFa_out) != len(OrbDFb_out):
        print("WARN : OrbDF_common_epoch_finder : len(OrbDFa_out) != len(OrbDFb_out)")
    
    if return_index:
        return OrbDFa_out , OrbDFb_out , Iinter
    else:
        return OrbDFa_out , OrbDFb_out


def OrbDF_const_sv_columns_maker(OrbDFin,inplace=True):
    """
    (re)generate the const and sv columns from the sat one
    """
    if inplace:
        OrbDFin['const'] = OrbDFin['sat'].str[0]
        OrbDFin['sv']    = OrbDFin['sat'].apply(lambda x: int(x[1:]))
        return None
    else:
        OrbDFout = OrbDFin.copy()
        OrbDFout['const'] = OrbDFout['sat'].str[0]
        OrbDFout['sv']    = OrbDFout['sat'].apply(lambda x: int(x[1:]))
        return OrbDFout

 #   _____ _      _____   __      __   _ _     _       _   _             
 #  / ____| |    |  __ \  \ \    / /  | (_)   | |     | | (_)            
 # | (___ | |    | |__) |  \ \  / /_ _| |_  __| | __ _| |_ _  ___  _ __  
 #  \___ \| |    |  _  /    \ \/ / _` | | |/ _` |/ _` | __| |/ _ \| '_ \ 
 #  ____) | |____| | \ \     \  / (_| | | | (_| | (_| | |_| | (_) | | | |
 # |_____/|______|_|  \_\     \/ \__,_|_|_|\__,_|\__,_|\__|_|\___/|_| |_|
                                                                       

def stats_slr(DFin,grpby_keys = ['sat'],
              threshold = .5):
    """
    computes statistics for SLR Residuals
    
    Parameters
    ----------
    DFin : Pandas DataFrame
        Input residual Dataframe from read_pdm_res_slr.
    grpby_keys : list of str, optional
        The default is ['sat'].
        per day, per solution, per satellite: ['day','sol','sat']
        per day, per solution, per station: ['day','sol','sta']
        per day, per solution, per satellite, per station: ['day','sol','sta','sat']
    threshold : float
        apply a Threshold

    Returns
    -------
    DD : Output statistics DataFrame
        return the mean, the rms and the std.
    """
    
    DD = DFin[np.abs(DFin["res"]) < threshold]
    
    DD_grp  = DD.groupby(grpby_keys)
    DD_mean = DD_grp['res'].agg(np.mean).rename('mean') * 1000
    DD_rms  = DD_grp['res'].agg(stats.rms_mean).rename('rms')   * 1000
    DD_std  = DD_grp['res'].agg(np.std).rename('std')   * 1000
    DD = pd.concat([DD_mean,DD_std,DD_rms],axis=1)
    DD.reset_index(inplace = True)
    
    return DD    
