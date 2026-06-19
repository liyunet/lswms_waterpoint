#!/usr/bin/env python
# coding: utf-8


"""
Primary script for the WaterPoint water balance model simulation.

This module implements the core logic for simulating the WaterPoint water 
balance model, designed for deployment within the rangeland monitoring platform. With some modification
it is built up on with the concept with the USGS waterpoint model but here we utlized open-source
packages as it is going to be utlized in governement office. In addition, the time to run the model
is optmized and it is built to handle lengthy, multi-year simulations efficiently in an 
open-source environment. c

### Key Features:
* **Geospatial Integration:** Utilizes Python's geospatial packages to perform 
    all necessary location-based and spatial calculations.

* **Scalability:** Leverages **Dask** for parallel processing across multiple 
    data points and time steps, significantly enhancing computational efficiency 
    and reducing simulation time.

* **Environment:** Easily deployable and reproducible. All required dependencies 
    can be installed using a standard Conda environment setup.
* **Operating System:** works fine on all operating systems.  

This script serves as the main entry point for running the simulation 
and producing the daily water point results.
"""
# Import  libraries

import sys
import os
import configparser
import datetime as DT
from pathlib import Path
import pathlib
import warnings 
import numpy as np
import pandas as pd 
import geopandas as gpd
import xarray as xr
# import xrspatial as xrs # Keep if xrspatial features are needed elsewhere
import rioxarray as rxr
import rasterio as rio
from rasterio.enums import Resampling
from rasterio.warp import calculate_default_transform, reproject
from pyproj import CRS
from pyproj.transformer import Transformer
from dateutil.relativedelta import relativedelta # Added missing import
from rasterstats import zonal_stats # Keep this if it's the intended zonal stats function
import requests
# Import user-defined modules
# Determine base paths based on OS (for linux and windows)
base_path = Path.cwd()
print(f"Base path set to: {base_path}")
sys.path.append(base_path)
from utils import zips,print_msg
from main_config import load_config,ConfigRetriever
#import workspace manger module which has methods to import dataframes, manage workspace with creating the env dirs and get_run_dates 
from  workspace_dates_mngr import workspace_dates_arg
import warnings
warnings.filterwarnings("ignore")



#set logging 
current_time = DT.datetime.today()
run_date = current_time.strftime("%Y-%m-%d")
timestamp = current_time.strftime("%Y-%m-%d_%H_%S")
log_filename = f"log_{timestamp}.txt"
log_path = base_path.parent.joinpath(f"logs/{run_date}")
log_path.mkdir(parents=True,exist_ok = True)
# with open(log_path.joinpath(log_filename), "w") as file:
#     file.write("Log file created successfully.\n")
logger = print_msg.setLogger(log_path.joinpath(log_filename))
logger.info("logging started .........")



#load config files : path, extensions,db
config = load_config(base_path.joinpath("conf"))
#access the attributes of each config files with ConfigRetriever class
config_attrs = ConfigRetriever(config)
#load file extensions from conf/config
zip_ext = config_attrs.config['FileExtensions']['zip_ext']
bil_ext = config_attrs.config['FileExtensions']['bil_ext']
#Load configuration details, including crucial scaling, data path, workspace, and projection parameters, from the conf/config file
mm_scale_factor = float(config_attrs.config['wp_conf']['mm_scale_factor'])
mm_conv_factor = float(config_attrs.config['wp_conf']['mm_conv_factor'])
target_crs = CRS.from_wkt(config_attrs.config['wp_conf']['prj4_string'])
#load dataframe Paths from conf/config
wp_coords = base_path.parent.joinpath(config_attrs.config['Paths']['wp_coords'])
rfe_temp_path =  base_path.parent.joinpath(config_attrs.config['Paths']['rfe_temp_path'])
RFE_path = base_path.parent.joinpath(config_attrs.config['Paths']['RFE_path'])
#rfe_pickle_path = base_path.parent.joinpath(config_attrs.config['Paths']['rfe_pickle_path'])
# final_Depth = base_path.parent.joinpath(config_attrs.config['Paths']['final_depth_pkl'])
# log_path = base_path.parent.joinpath(config_attrs.config['Paths']['logs_dir'])
url = config_attrs.config['SystemConfig']['url'] 
content = config_attrs.config['SystemConfig']['Content_type'] 
auth = config_attrs.config['SystemConfig']['Authorization'] 
headers = {}
headers['Content-type']= content
headers['Authorization']= auth



#the class is initiated with configuration attributes and the base path 
workspace = workspace_dates_arg(base_path=base_path,config_attrs=config_attrs,logger=logger) 
#mange workspace 
wrk_dirs =workspace.manage_workspace()
#retieve dataframes  
dataframes = workspace.get_dataframes()
recent_download = workspace.download_rfe()
print(recent_download)
date_lists,final_Depth = workspace.get_run_dates()
date_lists = pd.date_range(date_lists[0],recent_download)
# date_lists = pd.date_range(date_lists[0],recent_download)
# date_lists = date_lists[36: ]
date_lists



# --- Load model paramertes from loc_sample ---
loc_sample_df = dataframes['loc_pickle_path']  #retrieve the loc dataframe 
if loc_sample_df.empty:
    logger.error(f"No data found in the dataframe loc_sample_df")
    raise ValueError(f"Failed to load the model parameters necessary to run the waterpoint model.")
elif 'uid' not in loc_sample_df.columns:
    logger.error("'uid' column is missing in loc_sample_df.")
    raise ValueError("'uid' column is missing in loc_sample_df.")
loc_sample_df['uid'] = loc_sample_df['uid'].astype(int) # Match type with geometry


# Config read 

main_geometry_gdf = dataframes['shapes_path_WGS'][['uid', 'geometry']]
main_geometry_gdf['uid'] = main_geometry_gdf['uid'].astype(int) 

clet_path = base_path.parent.joinpath(config_attrs.config['Paths']['clet_path'])

def process_ET(target_date, clet_path,logger) :
    #clet_path clet_180101 to clet_181231
    """
    Extracts and processes Evapotranspiration (ET) data for zonal statistics.
    This function reads the daily Climate Evapotranspiration (CLET) raster file 
    corresponding to the `target_date`, performs zonal statistics against a 
    pre-defined geometry (e.g., a shapefile), and processes the results.

    The function assumes the ET data is already in a user-defined projection from 
    USGS, and no reprojection is required.

    Parameters
    ----------
    target_date : datetime.date or str
        The specific date for which the CLET data should be processed.
    clet_path : str
        The file path to the CLET data directory or the specific daily CLET file. 
        (Files are typically named following a pattern like 'clet_YYMMDD').
    logger : logging.Logger
        A logger instance for tracking execution status.
        
    Returns
    -------
    pandas.DataFrame
        A DataFrame containing the daily ET zonal statistics (daily climate-ET), 
        with one row per zone (e.g., location or waterpoint).

    Raises
    ------
    FileNotFoundError
        If the CLET file for the `target_date` is not found at the specified path.
    """
    # print(target_date)
    month_tt = target_date.month
    day_tt = target_date.day
    # print(day_tt)
    # The filename format is clet_18MMdd/
    month_str = f"{month_tt:02d}"
    day_str = f"{day_tt:02d}" #
    #from clet_180101
    clet_file_name = f"clet_18{month_str}{day_str}"
    #print('clet filename ', clet_file_name)
    clet_path_proc = clet_path / clet_file_name
 
    try:
        src_clet = rio.open(clet_path_proc)
        logger.info(f"reading ET files {clet_file_name}")
        clet_affine=src_clet.transform
        clet_array=src_clet.read(1)
        
        stats = zonal_stats(main_geometry_gdf, clet_array, affine=clet_affine,stats=['mean'],all_touched=True,
            nodata=src_clet.nodata)
        logger.info(f"{clet_file_name} ET zonal statistics calculated successfully ")
        # Extract the zonal stat results and append to list
        list_et=[]
        for idx, row in main_geometry_gdf.iterrows(): #has two cols 'uid', 'geometry'
            uid = row['uid']
            mean_et_mm = stats[idx]['mean'] 
            M_Day = int(clet_file_name[7:])
            # mm_scale, scale et from mm to m 
            mean_rain_m = mean_et_mm * mm_scale_factor
            vals=np.array([uid, mean_rain_m, M_Day])
            list_et.append(vals)
        df = pd.DataFrame(list_et,columns=['uid', 'Evap(m)', 'm_day'])

        return df
    except OSError as e:
        logger.error('Failed to read the ET raster file {clet_file_name} for {target_date}')
        return None


print(clet_path)



#call the process_ET function and process the zonal status for defined geometry(shapes, waterpoints)
list_clet = []
processed_dates_count = 0
logger.info(f'====================processing ET============================================================================')
for current_date in date_lists:
    vals = process_ET(current_date,clet_path,logger=logger) #call the zonal stat function here and retrive with val for each target date
    list_clet.append(vals)
    processed_dates_count += 1
    print(processed_dates_count)
clet_data = pd.concat(list_clet)
# clet_data = pd.DataFrame(list_clet,columns=['uid', 'Evap(m)', 'm_day'])
clet_data['uid'] = clet_data['uid'].astype('int')
clet_data['m_day'] = clet_data['m_day'].astype('int')
logger.info(f"processed ET for {processed_dates_count} days ")

# load the existing clet data and merge with the new
#comment here i have to check the data and go with the exitisting one. avoid cimporting  the clet data pkl.
if not all(col in clet_data.columns for col in ['uid', 'm_day', 'Evap(m)']):
    raise ValueError("CLET data frame missing required columns: 'uid', 'm_day', 'Evap(m)'")
if len(clet_data['m_day'].values)>=1:
    clet_data.sort_values(by=['uid', 'm_day'], inplace=True)
    clet_data['m_day'] = clet_data['m_day'].astype(int)
    # should figure out to use for all dataframes to be manged by lookup table)
    clet_et_map = clet_data.set_index(['uid', 'm_day'])['Evap(m)'].to_dict()
else:
    raise RuntimeError("No data to process:ET dataframe is empty")



# RFE Data Preparation
def rfe_prep(target_date, rfe_base_path, temp_extract_path,logger):
    """
        Prepares Rainfall Estimate (RFE) data for processing.

        The main task of this function is to locate, unzip, and extract the 
        RFE data file (usually a .bil file) corresponding to the specified 
        target date from the base RFE archive path.

        Parameters
        ----------
        target_date : datetime.date 
            The specific date for which the RFE data is required (e.g., 'YYYY-MM-DD').
        rfe_base_path : str
            The root directory containing the compressed RFE archive files.
        temp_extract_path : str
            The temporary directory where the extracted .bil file will be placed.
        logger : logging.Logger
            A logger instance for tracking execution status.
            
        Returns
        -------
        str
            The full path to the extracted RFE .bil file, or None if the file 
            could not be found or extracted.
            
        Raises
        ------
        FileNotFoundError
            If the compressed RFE archive for the target date is not found 
            in the `rfe_base_path`.
    """
    year = target_date.strftime("%Y")
    tt = target_date.timetuple()

    # julian day format to extract the zip rain_20011.tar
    julian_day_str = int('%d%0d' % (tt.tm_year, tt.tm_yday)) #f"{tt.tm_yday:02d}" #
    rain_zip_name = f"rain_{julian_day_str}{zip_ext}"
    rain_zip_path = rfe_base_path / year / rain_zip_name

    # rain_file_name = f"rain_{year}{julian_day_str}{bil_ext}" # Alternative format
    rain_file_name = f"rain_{julian_day_str}{bil_ext}"
    expected_bil_path = temp_extract_path / rain_file_name

    if not rain_zip_path.is_file():
        logger.error(f"RFE Zip file not found for {target_date}: {rain_zip_path}")
        return None
    try:
        zips.unzipTar(rain_zip_path, temp_extract_path) 
        logger.info(f"Unzipping to {temp_extract_path}")
    except Exception as e:
        logger.error(f"unziping {rain_zip_path} enountered an Error : {e}")
        return None

    rain_bil_path = temp_extract_path / rain_file_name
    if rain_bil_path.is_file():
        logger.info(f"path to RFE BIL file: {rain_bil_path}")
        return rain_bil_path
    else:
        #logging is crucial here, Will copy from USGS original
        logger.error(f"unabale to find BIL file '{rain_file_name}' in {temp_extract_path}")
        return None




# Here we rfe_prep function is called to prepare and processe the RFE to user-defined projection. 
# calculate the zonal stat 
print(f"Processing RFE data from {date_lists[0]} to {date_lists[-1]}...")
list_rfe_prep = []
procsd_dates_count = 0
#/////
list_df = []
uid_list = main_geometry_gdf.uid.values
wp_crds = pd.read_csv(wp_coords)
coord_list = [(x, y) for x, y in zip(wp_crds.x_coord, wp_crds.y_coord)]
logger.info(f'====================processing Rainfall the=====================================================================')

print("processing Rainfall")

for current_date in date_lists:
    logger.info(f'processing for {current_date}')
    rain_bil_path = rfe_prep(current_date, RFE_path, rfe_temp_path,logger=logger)

    if rain_bil_path is None:
        raise FileNotFoundError
    try:
        #extract waterpoints rainfal before projection
        src = rio.open(rain_bil_path)
        df=pd.DataFrame()
        df['uid'] = uid_list
        df['date'] = current_date
        df["RFE"] = [x for x in src.sample(coord_list)]
        df["RFE"] = df["RFE"]*0.001 
        list_df.append(df)
        # Open raster and reproject ONCE per date
        with rxr.open_rasterio(rain_bil_path) as rain_raw:
            rain_raw = rain_raw.squeeze(drop=True) # Remove single dimensions
            print(f"Reprojecting to UserDefined CRS: {target_crs.to_string()}")

            if rain_raw.rio.crs is None:
                 warnings.warn(f"Source CRS for {rain_bil_path} is missing.")
                 rain_raw.rio.write_crs("EPSG:4326", inplace=True)
            # reprojection to user defined projection
            rain_proj = rain_raw.rio.reproject(target_crs, resampling=Resampling.nearest)
            print(f"Reprojection  is done. Shape: {rain_proj.shape}")
            affine = rain_proj.rio.transform()
            rain_data_np = rain_proj.values # Get numpy array for zonal_stats

            # Check if values of the rain projection is valid or all nan
            if np.isnan(rain_data_np).all():
                 warnings.warn(f" the values are all NaN for date {current_date}")
                 continue

            # Calculate zonal stats for the watersheds (only 6 waterpoints are managed for this simulation)
            #here both rainfall and main_geometery should be on the same projection to process zonal
            if main_geometry_gdf.crs != rain_proj.rio.crs:
                main_geometry_gdf = main_geometry_gdf.to_crs(rain_proj.rio.crs)

            stats = zonal_stats(main_geometry_gdf,rain_data_np,affine=affine,stats=['mean'], all_touched=True,
                nodata=rain_proj.rio.nodata) 
            # Extract results and append to list
            for idx, row in main_geometry_gdf.iterrows():
                uid = row['uid']
                mean_rain_mm = stats[idx]['mean'] # Assuming rain is in mm initially
                # Convert rain from RFE mm to meters 
                # scalefactor will be included for other data sources like CHIRPS
                mean_rain_m = mean_rain_mm * 0.001
                list_rfe_prep.append([uid, mean_rain_m, current_date])
            procsd_dates_count+= 1
    except rio.RasterioIOError as e:
        logger.error(f"Error proccessing the raster {rain_bil_path}: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred  {current_date}: {e}")
        sys.exit(1)
        # I will add the logging from USGS_code here for easy error logging 
        
#waterpoint RFE data extraction: the results are stored in a dataframe.
rfe_waterpoint_df = pd.concat(list_df, ignore_index=True)
if rfe_waterpoint_df.empty :
    logger.error(f"No data found in the dataframe rfe_waterpoint_df. Cannot run the waterpoint model.")
    raise ValueError(f"No data found to run the waterpoint model") 
else:
    rfe_waterpoint_df['RFE'] = rfe_waterpoint_df['RFE'].apply(lambda x : x.item())
    rfe_waterpoint_df['date']=pd.to_datetime(rfe_waterpoint_df.date).dt.date 
rfe_watershed_df = pd.DataFrame(list_rfe_prep, columns=['uid', 'Rain(m)', 'date'])

#zonal stat is calculated for the RFE data and the results are stored in a dataframe.
if rfe_watershed_df.empty :
    logger.error(f"No data found in the dataframe rfe_watershed_df. Cannot run the waterpoint model.")
    raise ValueError(f"No data found to run the waterpoint model") 
else:
    rfe_watershed_df['date']=pd.to_datetime(rfe_watershed_df.date).dt.date 

logger.info(f"Waterpoint and watershed RFE extraction and reading completed successfully for: {procsd_dates_count} dates.")


rfe_watershed_df.head()


print("========================start the simulation=======================================")
class Wp_run: #we need object or none for the class /implmentation
    """
        Initializes the WaterPoint (WP) simulation model runner.

        This model integrates various pre-processed inputs, including location 
        parameters, zonal evapotranspiration data, and waterpoint and zonal rainfall/RFE estimates, with 
        static site calibration parameters to prepare for the simulation run. 
        Note: it can be run parallel and it will be soon available

        Parameters
        ----------
        loc_params_df : pandas.DataFrame
            Location-specific model parameters (water_depth, Alpha and Water_use) the result of the calibration.
        clet_et_map : dict
            Dictionary mapping (uid, m_day) to Evap(m).
            Evapotranspiration (ET) data, pre-processed for CLET.
        rfe_data_final : pandas.DataFrame
            Final processed Rainfall Estimate (RFE) data.
        df_wps_RFE : pandas.DataFrame
            Water points mapped to their corresponding RFE data.
        final_Depth : pandas.DataFrame 
            Static parameters, including initial water depths or similar metrics.
        headers : dict
            HTTP headers required for API communication (e.g., authentication).
        url : str
            The URL for the platform API endpoint.
        logger : logging.Logger
            A logger instance for tracking execution status and errors.
            used the exisitng logging file from USGS with some modification
    """
            
    def __init__(self, loc_params_df, clet_et_map,rfe_watershed_df,rfe_waterpoint_df,final_Depth,headers,url,logger):
        """
        Args: class init with the arguments or parameters  defiend above in the class 

        """
        # Set index for faster lookup if processing multiple UIDs
        self.logger = logger
        self.headers = headers
        # url = 'https://rangelandmonitoring.eiar.gov.et:5001/api/v1/monitored/dialy_update'
        url ='https://webapi.waterpointsmonitoring.net/api/v1/monitored/dialy_update'
        self.url = url
        self.loc_params = loc_params_df.set_index('uid') #access theparameters by filtering with uid(waterpoin_ID)
        self.clet_et_map = clet_et_map
        self.rfe_watershed_df = rfe_watershed_df
        self.rfe_waterpoint_df = rfe_waterpoint_df
        self.final_Depth = final_Depth
        self.seapage = 0.002 
        # xx= self.rfe_df.date.values
        #the two static methods can be outside the class  
    @staticmethod 
    def check_depth(water_level, max_depth):
        """
        This function is static and it ensures the water level is between zero and the maximum depth.
            Parameters
            ----------
            water_level : float
                The calculated (unbounded) water level from the simulation step.
            max_depth : float
                The maximum depth from location dataframe.  
            Returns: float
        """
        water_level = max(0.0, water_level) 
        water_level = min(water_level, max_depth) 
        return water_level
    @staticmethod
    def get_monDay(target_date):
        """Formats month and day as integer mmdd i.e 1201,0101, etc"""
        return int(f"{target_date.month}{target_date.day:02d}")
    @staticmethod
    def scaled_depth(df_depth):
        """
            Calculates the water depth scaled to a percentage (0-100) per waterpoint.
            The depth is normalized against the maximum depth observed within each 
            'location_id'. The calculated value is added as a new column as 'scaled_depth'.
            Parameters
            ----------
            df_depth : pandas.DataFrame 
            Returns
            -------
            pandas.DataFrame
                The input DataFrame including the new 'scaled_depth' column.
        """
        lists_df_depth_loc = []
        for loc_id in df_depth.location_id.unique():
            df_depth_loc=df_depth[df_depth['location_id']==loc_id]
            df_depth_loc['scaled_depth']=(df_depth_loc['depth']/df_depth_loc['depth'].max())*100
            lists_df_depth_loc.append(df_depth_loc)
        df_scaled_all =pd.concat(lists_df_depth_loc)
        return df_scaled_all
    
    def run_model_wp(self):
        """Executes the daily WaterPoint water balance simulation.

        This function iterates through each waterpoint and, for all available dates, 
        calculates the daily water depth (depth(m)) using a water balance equation.

        The core calculation is iterative, deriving the current day's depth from the 
        previous day's depth and accounting for daily inputs and outputs.

        The function handles special cases, including:
        * **Initial Day (2001-01-01):** Depth is set to 'Init_Depth' parameter as the simulation is starting from here.
        * **Dry Season (Jan, Feb, Jun, Jul, Aug, Dec):** Includes the 'Water_Use' parameter.
        * **Depth Bounds:** The result is bounded between 0 and max depth of the waterpoint.

        Parameters
        ----------
        self : Wp_run
            The instance containing pre-processed RFE data (`self.rfe_df`), 
            location parameters (`self.loc_params`), and ET data (`self.clet_et_map`).
            
        Returns
        -------
        pandas.DataFrame
            A DataFrame containing the daily simulation results for all processed 
            waterpoints and which will be formated on the next function.
        """
        rfe_df = self.rfe_watershed_df.sort_values(by='date')
        rfe_df_copy=rfe_df.copy()
        rfe_df_copy['depth(m)']=np.nan
        df_list = []
        self.logger.info("=========================================================================")
        self.logger.info("Running the model with the dates currently available for each waterpoint.")
        for wp_uid in rfe_df_copy.uid.unique():
             # rfe_df = rfe_df.sort_values(by=['uid', 'date'])
            self.logger.info(f"Processing the daily water level for waterpoint uid {wp_uid}")
            try:
                loc_params = self.loc_params.loc[wp_uid]
                wsh_area = loc_params['wshed_m2'] #watershade area in sq m 
                wp_area = loc_params['wp_m2'] #waterpoint area in sq m 
                water_depth_max = loc_params['Water_Depth'] #the max depth for 6 waterpoints while the rest will remain @2meters
                # print('water_depth_max',water_depth_max,wp_uid)
                water_use = loc_params['Water_Use']
                alpha = loc_params['Alpha']
                self.logger.info("Parameters for water level calculation loaded successfully. ")
            except KeyError:
                self.logger.error(f"Warning: Parameters for uid(waterpoint) {wp_uid} not found in loc_params. Skipping this UID.")
                rfe_df['depth(m)'] = np.nan
                return rfe_df_copy
            rfe_df_wp_uid = rfe_df_copy[rfe_df_copy.uid==wp_uid]
            rfe_df_wp_uid['date'] =pd.to_datetime(rfe_df_wp_uid['date']).dt.date
            date_list_df = rfe_df_wp_uid.date.unique()
            
            for i in range(0,len(rfe_df_wp_uid)):
                target_date = rfe_df_wp_uid['date'].iloc[i] 
                zrain = rfe_df_wp_uid['Rain(m)'].iloc[i]
                # Get evaporation for the specific month/day
                m_day = self.get_monDay(target_date)
                zevap = self.clet_et_map.get((wp_uid, m_day), 0.0) 
                # Calculate depth change from rainfall runoff
                volume = alpha * zrain * wsh_area
                depth_v = volume / wp_area
                if target_date == DT.date(2001,1,1):
                    RF = self.rfe_waterpoint_df[(self.rfe_waterpoint_df['date']== DT.date(2001,1,1)) & (self.rfe_waterpoint_df['uid']==wp_uid)]['RFE'].values[0]
                    # water_level = depth_v + RF - zevap - self.seapage
                    water_level= loc_params['Init_Depth']
                    # water_level = self.check_depth(water_level, water_depth_max)
                    rfe_df_wp_uid.loc[rfe_df_wp_uid.date == target_date,'depth(m)'] = water_level
                    rfe_df_wp_uid.loc[rfe_df_wp_uid.date == target_date,'evap(m)'] = zevap
                    self.logger.info(f"processed water level {wp_uid} for year 2001-01-01")
                    # print(target_date,wp_uid,water_level,zevap)

                #process the water level for dry season months 
                elif target_date.month in ([1,2,6,7,8,12]) and target_date != DT.date(2001,1,1):
                    prev_date = target_date + relativedelta(days=-1)
                # prev_depth = np.array(rfe_data[(rfe_data['uid'].iloc[i]==wp_uid) & (rfe_data['date'].dt.date==prev_date)]['depth(m)'])[0]
                    
                    if prev_date not in date_list_df:
                        prev_depth = np.array(self.final_Depth[(self.final_Depth['date']== prev_date) & (self.final_Depth['location_id'] == wp_uid)]['depth'])
                        
                    else:
                        prev_depth = np.array(rfe_df_wp_uid[rfe_df_wp_uid['date']==prev_date]['depth(m)'])
                        # prev_depth = np.array(rfe_df_wp_uid[rfe_df_wp_uid['date']==prev_date]['depth(m)'])
                    # print(target_date, 'wp id ----',wp_uid)
                    RF = self.rfe_waterpoint_df[(self.rfe_waterpoint_df['date']== target_date) & (self.rfe_waterpoint_df['uid']==wp_uid)]['RFE'].values
                    self.logger.info('the month is in the dry season and apply water use ', target_date.month)
                    water_level = RF + prev_depth + depth_v - zevap - water_use - self.seapage
                    water_level = self.check_depth(water_level, water_depth_max)
                    rfe_df_wp_uid.loc[rfe_df_wp_uid.date == target_date,'depth(m)'] = water_level
                    # rfe_df_wp_uid.loc[rfe_df_wp_uid.date == target_date,'prev_depth(m)'] = prev_depth
                    rfe_df_wp_uid.loc[rfe_df_wp_uid.date == target_date,'evap(m)'] = zevap
                    # print(target_date,wp_uid,prev_depth, water_level,zevap)

                else:
                    
                    prev_date = target_date + relativedelta(days=-1)
                    prev_date = pd.to_datetime(prev_date).date()
                    if prev_date not in date_list_df:
                        prev_depth = np.array(self.final_Depth[(self.final_Depth['date']==prev_date) & (self.final_Depth['location_id'] == wp_uid)]['depth'])
                    else:
                    # prev_depth = np.array(rfe_data[(rfe_data['uid'].iloc[i]==wp_uid) & (rfe_data['date'].dt.date==prev_date)]['depth(m)'])[0]
                        prev_depth = np.array(rfe_df_wp_uid[rfe_df_wp_uid['date']==prev_date]['depth(m)'])
                    RF = self.rfe_waterpoint_df[(self.rfe_waterpoint_df['date']== target_date) & (self.rfe_waterpoint_df['uid']==wp_uid)]['RFE'].values[0]
                    water_level = RF + prev_depth + depth_v - zevap - self.seapage
                    water_level = self.check_depth(water_level, water_depth_max)
                    rfe_df_wp_uid.loc[rfe_df_wp_uid.date == target_date,'depth(m)'] = water_level
                    # rfe_df_wp_uid.loc[rfe_df_wp_uid.date == target_date,'prev_depth(m)'] = prev_depth
                    rfe_df_wp_uid.loc[rfe_df_wp_uid.date == target_date,'evap(m)'] = zevap
                self.logger.info(f"processed water level for {target_date} for {wp_uid}")
            df_list.append(rfe_df_wp_uid)
        simulated_result_df = pd.concat(df_list)
        return simulated_result_df
    def format_output(self):
        print("==================================format output==============================================================")
        """Formats the results for platform upload.
            This method first calls 'self.run_model_wp()' to get the raw simulation results. 
            If successful, it performs the unit convesion for evap and Rain values from meters to millimeters.
            Formats the data section and column alignmet to prepare the data for the API. Then merges with historical and save
            to the hard disk.
            Returns
            -------
            pandas.DataFrame or None
                A DataFrame containing the final, formatted simulation results ready for 
                upload, filtered by the posting lag period, or None if the model run failed.
        """
        simulated_result_df = self.run_model_wp()
        if simulated_result_df is not None:
            # Convert the scaled evaporation and rainfall values back to millimeters (mm)
            simulated_result_df['date'] = pd.to_datetime(simulated_result_df.date)
            simulated_result_df['date'] = simulated_result_df.date.dt.date
            date_lists = simulated_result_df['date']
            simulated_result_df =simulated_result_df[['date','uid', 'Rain(m)',  'depth(m)', 'evap(m)']]
            #convert the evap and rainfall from m to mm 
            logger.info("converte evap and rainfall to mm to post to the platform ")
            simulated_result_df['evap(m)']=simulated_result_df['evap(m)']*mm_conv_factor
            simulated_result_df['Rain(m)']=simulated_result_df['Rain(m)']*mm_conv_factor
            logger.info("Adjust the month_day field format in simulated_results for API post  ")
            simulated_result_df['month_day'] = pd.to_datetime(simulated_result_df['date'])
            simulated_result_df['month_day']= simulated_result_df['month_day'].apply(lambda x: int(x.strftime('%m%d')))
            simulated_result_df['scaled_depth']=np.nan
            simulated_result_df = simulated_result_df[['uid', 'date', 'month_day','Rain(m)','evap(m)', 'depth(m)',  'scaled_depth']]
            columns_for_import = ['location_id', 'date', 'month_day', 'rain', 'evap', 'depth', 'scaled_depth']
            simulated_result_df.columns=columns_for_import
            #Merge the model run results with the existing final depth to append the scalling with the historical 
            self.final_Depth = pd.concat([self.final_Depth,simulated_result_df])
            self.final_Depth.drop_duplicates(subset=['location_id', 'date'], keep='last', inplace=True)
            self.final_Depth = self.scaled_depth(self.final_Depth)
            self.final_Depth.to_pickle(base_path.parent / "output" /"final_depth" / "simulated_results_df.pkl")
            logger.info("===============================Wp_run- Model run completed successfully============================================")
            #get the import data with lag time 2days
            posting_start_date=min(date_lists) + relativedelta(days=-2)
            df_import= self.final_Depth[self.final_Depth.date > posting_start_date]
            df_import['date']= pd.to_datetime(df_import.date).dt.date 
            return df_import  
    def upload_to_platform(self):
        """Uploads the daily waterpoint results to the platform's web API.

        This function serializes the input DataFrame to JSON, checks for a successful 
        connection with the platform's web server, and then uploads the data. 
        The API endpoint directly integrates with the platform database for 
        immediate access via the platform monitoring section.

        The upload time is dependent on the data volume; the function will block 
        until a success message is returned from the server.

        Parameters
        ----------
        df : pandas.DataFrame
            The DataFrame containing the daily waterpoint results to be uploaded.
        Returns
        -------
        bool
            True if the upload was successful and the server returned a success 
            status, False otherwise (e.g., connection error, server failure).
        Raises
        ------
        ConnectionError
            If the web server is unreachable or the initial connection check fails.
        """
        df_import = self.format_output()
        print(df_import.tail())
        json_data = df_import.to_json(orient='records')
        print(self.url)

        url ='https://webapi.waterpointsmonitoring.net/api/v1/monitored/dialy_update'
        # url = 'https://rangelandmonitoring.eiar.gov.et:5001/api/v1/monitored/dialy_update'
        response = requests.post(url, data=json_data, headers=headers,verify=False)
        print(response.status_code)
        if response.status_code==200:
            msg = f"upload processed successfully{response.status_code}"
            logger.info(f"data uploaded successfully, status code: {response.status_code}")
        else:
            msg = f"ERROR! upload was not successfull, status code: {response.text}"
            logger.error(msg)
        return msg



"""
Initialize the water point model with parameters loaded from the rain_prep, clet_prep, static parameters that are already available"
Methods:
    run_model_wp(): Executes the water point simulation.
    upload_to_platform(): Uploads simulation results to the web platform.
"""
run_model = Wp_run(loc_params_df=loc_sample_df, clet_et_map=clet_et_map,rfe_watershed_df=rfe_watershed_df,rfe_waterpoint_df=rfe_waterpoint_df,final_Depth=final_Depth,headers=headers, url=url,logger=logger)
#retrive the model result to simulated_results_df
# simulated_results_df = run_model.run_model_wp()
final_results_df= run_model.upload_to_platform()
print("==================================uploaded and it is done============================================================")
print("exiting the waterpoint model simulation and upload process" )



