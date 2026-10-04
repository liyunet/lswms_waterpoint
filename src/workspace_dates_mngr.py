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
            web = 'https://edcintl.cr.usgs.gov/downloads/sciweb1/shared/fews/web/africa/daily/rfe/downloads/daily/'
            
            geobil_path = self.base_path.parent.joinpath(self.config_attrs.config['Paths']['RFE_path'])
            url_rfe = self.config_attrs.config['SystemConfig']['url_rfe'] 
            year_ = datetime.today().year
            print(geobil_path)
            download_path = geobil_path.joinpath(str(year_))
            
            if not download_path.exists():
                download_path.mkdir(parents=True)
                
            os.chdir(download_path)
            print('current working directory', os.getcwd())
            
            lfiles = glob.glob("*.*", recursive=True)
            lag = 2

            download_date = datetime.today() - timedelta(days=lag)
            download_jdate = '%d%03d' % (download_date.today().timetuple().tm_year, download_date.timetuple().tm_yday)
            print('download_jdate', download_jdate)
            
            lfiles.sort(reverse=False)
            print('lfiles', lfiles[-5:])
            
            if len(lfiles) != 0:
                valid_jdates = []
                for i in lfiles:
                    if i.startswith("rain_") and i.endswith(".tar.gz"):
                        sub = i[5:-7]
                        if sub.isdigit():
                            valid_jdates.append(int(sub))
                
                if valid_jdates:
                    last_jdate = max(valid_jdates)
                else:
                    last_jdate = int(f"{year_}001")

                if last_jdate == int(download_jdate):
                    print(last_jdate)
                    print("the file is already downloaded")
                else:
                    date_start = datetime.strptime(str(last_jdate)[2:], "%y%j")
                    date_start = date_start + timedelta(days=1)
                    download_date = download_date.date()
                    date_range = pd.date_range(start=date_start, end=download_date)
                    
                    for i in range(len(date_range)):
                        julian_date = '%d%03d' % (date_range[i].timetuple().tm_year, date_range[i].timetuple().tm_yday)
                        file_name = "rain_{}.tar.gz".format(julian_date)
                        
                        if os.path.exists(file_name) and os.stat(file_name).st_size > 10000:
                            print(f"File {file_name} already exists and looks valid. Skipping download.")
                            continue
                            
                        url = "{}rain_{}.tar.gz".format(url_rfe, julian_date)
                        print(url)
                        try:
                            if os.path.exists(file_name):
                                os.remove(file_name)
                            wget.download(url, out=file_name)
                            print(f"\nSuccessfully downloaded {file_name}")
                        except Exception as e:
                            print(f'\nAttempting fallback URL for {julian_date} due to: {e}')
                            try:
                                url_fallback = "{}rain_{}.tar.gz".format(web, julian_date)
                                if os.path.exists(file_name):
                                    os.remove(file_name)
                                wget.download(url_fallback, out=file_name)
                                print(f"\nSuccessfully downloaded {file_name} from fallback.")
                            except Exception as e2:
                                print(f'RFE data for {date_range[i].date()} failed to download: {e2}')
            else:
                date_new = datetime(year_, 1, 1)
                julian_date = '%d%03d' % (date_new.timetuple().tm_year, date_new.timetuple().tm_yday)
                print("downloading zip file for julian date {}".format(julian_date))
                file_name = "rain_{}.tar.gz".format(julian_date)
                url = "{}rain_{}.tar.gz".format(web, julian_date)
                try:
                    wget.download(url, out=file_name)
                except Exception as e:
                    print(f'Initial RFE download failed: {e}')
            
            # Robust parsing for final return date
            lfiles = glob.glob("*.*", recursive=True)
            valid_jdates = [int(i[5:-7]) for i in lfiles if i.startswith("rain_") and i.endswith(".tar.gz") and i[5:-7].isdigit()]
            if not valid_jdates:
                raise ValueError("No valid RFE files found after download attempt.")
                
            last_jdate = max(valid_jdates)
            last_jdate_str = str(last_jdate)
            print(last_jdate_str)
            data_avail_date = datetime(int(last_jdate_str[:4]), 1, 1) + timedelta(days=int(last_jdate_str[4:]) - 1)
            return data_avail_date
                                                                                                                                                                                      
#path_='/home/liam/FEWS/DataPortal_dev/data/Africa/Daily/RFE/geobil/'