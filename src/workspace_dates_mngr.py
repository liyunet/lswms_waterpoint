#this script creates workspace and return the run dates to process the waterpoint daily modeling
# reat temp and depth dirs if they are not created
# I will integrate the logger from the existing logger 
from dateutil.relativedelta import relativedelta
from datetime import datetime,timedelta
import pandas as pd
import geopandas as gpd
import sys
import wget
import pathlib
from pathlib import Path
import os
import requests
import glob
#import logging 
        # self.logger = logging.getLogger(name)
        # self.logger.info("Initialized %s with value: %s", name, value)
#load config files : path, extensions,db

class workspace_dates_arg:
    def __init__(self,base_path,config_attrs,logger):#
        # Setup logging
        self.logger = logger
        self.base_path = base_path
        self.config_attrs = config_attrs

    def manage_workspace(self):
        paths_to_create = [
                'final_depthDB_path', 
                'temp_workspace_path',
                'rain_proj_path', 
                'rfe_temp_path',
                
            ]
            
        created_paths = {}
        try:
            for path_key in paths_to_create:
                path = self.base_path.parent.joinpath(self.config_attrs.config['Paths'][path_key])
                path.mkdir(parents=True,exist_ok = True)
                self.logger.info(f"Created workspace directory: {path}")
                created_paths[path_key]= path
            return created_paths 
        except Exception as e:
            self.logger.error("Error in directory creation due to: %s", e)
            sys.exit(1)
            return (f"errer occured {e}")
    def get_dataframes(self):
        dataframe_paths = ['loc_pickle_path',
                           'shapes_path_WGS',
                        ] #'clet_pickle_path', 'wp_rfe_pickle_path' 'rfe_pickle_path'
        df_pickles= {}
        try:
            # rfe_data = pd.read_pickle(rfe_pickle_path) # Loading this later after potentially reprocessing
            for path_key in dataframe_paths:
                if path_key == 'shapes_path_WGS':
                    df = gpd.read_file(self.base_path.parent.joinpath(self.config_attrs.config['Paths'][path_key]))
                else:
                    df = pd.read_pickle(self.base_path.parent.joinpath(self.config_attrs.config['Paths'][path_key]))
                self.logger.info(f"successfully read dataframe : {path_key}")
                df_pickles[path_key] = df   
            return  df_pickles
        except FileNotFoundError as e:
            self.logger.error(f"Required data file not found: {e}")
            raise FileNotFoundError(f"Required data file not found: {e}") from e
            
    def get_run_dates(self):
        try:
            final_depth_pkl = self.base_path.parent.joinpath(self.config_attrs.config['Paths']['final_Depth_pkl'])
            final_depth_df = pd.read_pickle(final_depth_pkl)
            final_depth_df['date'] = pd.to_datetime(final_depth_df['date'])
            max_date= final_depth_df.date.max()
            #added for test
            # imported_date = datetime(2025,11,18)
            final_depth_df=final_depth_df[final_depth_df.date < max_date]
            #ends here
            imported_date = final_depth_df['date'].max()+ relativedelta(days=1)
            run_date = datetime.today().date()
            lag_date = run_date + relativedelta(days=-2)
            date_list = pd.date_range(start=imported_date, end=lag_date, freq='D').date # Get list of dates
            final_depth_df['date'] = final_depth_df.date.dt.date
            self.logger.info(f"Processing dates are from {imported_date} to {lag_date}")
            return date_list,final_depth_df
        except FileNotFoundError as e:
            self.logger.error("Required data from final_Depth_pkl not found: %s", e)
            raise FileNotFoundError(f"Required data file not found: {e}") from e 
    def download_rfe(self):
        
        # path_ = pathlib.Path.cwd().joinpath("geobil")
        # url_o ='https://edcintl.cr.usgs.gov/downloads/sciweb1/shared/fews/web/africa/daily/rfe/downloads/daily/'
        
        geobil_path = self.base_path.parent.joinpath(self.config_attrs.config['Paths']['RFE_path'])
        url_rfe = self.config_attrs.config['SystemConfig']['url_rfe'] 
        year_= datetime.today().year
        #year_=datetime.datetime(2025,3,1).year
        print(geobil_path)
        download_path =geobil_path.joinpath(str(year_))
        os.chdir(download_path)
        lfiles = glob.glob("*.*",recursive=True)
        lag=2

        if not(download_path.exists()):
            download_path.mkdir(parents=True)
        #download_date=datetime.datetime.today()- datetime.timedelta(days=lag)
        download_date= datetime.today()- timedelta(days=lag)
        download_jdate='%d%03d' % (download_date.today().timetuple().tm_year,download_date.timetuple().tm_yday)
        #lfiles = [int(str(x)[70:-7]) for x path = Path(output_path).glob('**/*')in path if x.is_file()]
        if len(lfiles) != 0:
            last_jdate= max([int(i[5:-7]) for i in lfiles ])
            if last_jdate==int(download_jdate):
                print(last_jdate)
                print("the file is already downaloded")
            else:
                date_start= datetime.strptime(str(last_jdate)[2:], "%y%j")
                date_start=date_start+timedelta(days=1)
                download_date=download_date.date()
                date_range=pd.date_range(start=date_start, end=download_date)
                #date_range=pd.date_range(start='2025-03-01', end='2025-05-25')
                for i in range(len(date_range)):
                    #julian_date='%d%03d' % (date_range[i].timetuple().tm_year,date_range[i].timetuple().tm_yday)
                    julian_date='%d%d' % (date_range[i].timetuple().tm_year,date_range[i].timetuple().tm_yday)
                    url="{}rain_{}.tar.gz".format(url_rfe,julian_date)
                    print(url)
                    try:
                        wget.download(url)
                        d_size = requests.get(url,stream=True)
                        d_size =  int(d_size.headers.get("Content-length"))
                        f_size = os.stat("rain_{}.tar.gz".format(julian_date)).st_size
                        while (f_size != d_size):
                            print ('the downlaoded file is corrupted, downaloding in progress')
                            os.remove("rain_{}.tar.gz".format(julian_date))
                            print("downloading  again julian date {}".format(julian_date))
                            url="{}rain_{}.tar.gz".format(web,julian_date)
                            f_size = os.stat("rain_{}.tar.gz".format(julian_date)).st_size
                    except  Exception as e:
                        print(f'RFE data for {download_date} may not be avaialble, please try again later: {e}')
        else:
            date_new=datetime.date(year_,1,1)
            julian_date='%d%d' % (date_new.timetuple().tm_year,date_new.timetuple().tm_yday)
            print("downloading zip file for julian date {}".format(julian_date))
            url="{}rain_{}.tar.gz".format(web,julian_date)
            wget.download(url)
            d_size = requests.get(url,stream=True)
            d_size =  int(d_size.headers.get("Content-length"))
            f_size = os.stat("rain_{}.tar.gz".format(julian_date)).st_size
            while (f_size != d_size):
                print ('the downlaoded file is corrupted, downaloding in progress')
                os.remove("rain_{}.tar.gz".format(julian_date))
                print("downloading  again julian date {}".format(julian_date))
                url="{}rain_{}.tar.gz".format(web,julian_date)
                f_size = os.stat("rain_{}.tar.gz".format(julian_date)).st_size
        
        lfiles = glob.glob("*.*",recursive=True)
        last_jdate= max([int(i[5:-7]) for i in lfiles ])
        last_jdate = str(last_jdate)
        print(last_jdate)
        data_avail_date = datetime(int(last_jdate[:4]), 1, 1) + timedelta(days=int(last_jdate[4:]) - 1)
        return data_avail_date
                                                                                                                                                                                      
#path_='/home/liam/FEWS/DataPortal_dev/data/Africa/Daily/RFE/geobil/'