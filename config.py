import os, platform, configparser

HOME_DIR = os.environ["USERPROFILE"] if platform.system() == "Windows" else os.environ["HOME"]
config_file_full_path = os.path.join(HOME_DIR, "dhs622_config.cfg")
config = configparser.ConfigParser()
config.read(config_file_full_path)

insta_username = config["instagram"]["username"]
insta_password = config["instagram"]["password"]