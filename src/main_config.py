# Read config values
import configparser
from pyproj import CRS
def load_config(base_path):
    """
    Load config file with base_path parameter
    """
    #path to the configuration file
    config_path = base_path / 'conf.conf'
    
    # check the config files here
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found at {config_path}")
    
    # Read the configuration
    config = configparser.ConfigParser()
    config.read(config_path)
    
    return config


class ConfigRetriever:
    """
    Retrieves and sets configuration attributes from a configparser object.
    """
    def __init__(self, config):
        # Store the config object itself, if needed
        self.config = config
        
        try:
            # === [wp_conf] section attributes ===
            self.dataset_region = config.get('wp_conf', 'dataset_region')
            self.DS_TYPE = config.get('wp_conf', 'DS_TYPE')
            self.prj_file_name = config.get('wp_conf', 'prj_file_name')
            self.final_depth_grid_prefix = config.get('wp_conf', 'final_depth')
            
            # Retrieve conversion and scale factors
            self.scale_factor_wp = int(config.get('wp_conf', 'scale_factor_wp'))
            self.scale_factor_wsh = int(config.get('wp_conf', 'scale_factor_wsh'))
            self.mm_scale_factor = config.get('wp_conf', 'mm_scale_factor')
            self.mm_conv_factor = int(config.get('wp_conf', 'mm_conv_factor'))
            # Process CRS string (requires pyproj.CRS import)
            self.prj4_string = config.get('wp_conf', 'prj4_string')  # Keep the string version
            # === file extension 
            self.bil_ext = config.get('FileExtensions', 'bil_ext')
            self.zip_ext = config.get('FileExtensions', 'zip_ext')
            #=====config files ===========
            self.url = config.get('SystemConfig','url')
            self.content = config.get('SystemConfig','Content_type')
            self.auth = config.get('SystemConfig','Authorization')
            self.url_rfe = config.get('SystemConfig','url')

            #--pickle files 
            #remved the the two lines below as they are not used in the code
            # self.loc_pickle_path = config.get('Paths','loc_pickle_path')
            # self.clet_pickle_path = config.get('Paths','clet_pickle_path')
            # self.wp_rfe_pickle_path  = config.get('Paths','wp_rfe_pickle_path')
            self.final_Depth_pkl = config.get('Paths','final_Depth_pkl')
            #workspace 
            self.rain_proj_path = config.get('Paths','rain_proj_path')
            self.final_depthDB_path = config.get('Paths','final_depthDB_path')
            self.rfe_temp_path = config.get('Paths','rfe_temp_path')
            self.temp_workspace_path = config.get('Paths','temp_workspace_path')
            self.logs_dir = config.get('ProjectStructure','logs_dir')
           
        except configparser.NoOptionError as e:
            # Raise a custom error with better context for debugging
            raise ValueError(f"Missing configuration option: {e.section} -> {e.option}") from e
        except ValueError as e:
            # Catch errors from int() conversion or CRS processing
            raise ValueError(f"Error processing a configuration value: {e}") from e



