import os
import requests
from math import log, tan, cos, pi, radians
from tqdm import tqdm
from yaml import safe_load
from os import environ
from os.path import join as join_path, expanduser
from sys import exit
import logging

'''
Author: DRoBeR <24878299+droberin@users.noreply.github.com>
You need an API key from a valid account from https://www.thunderforest.com/docs/apikeys/
They offer them for free for hobbies projects. DO NOT ABUSE IT!
This script would try to avoid downloading existing files to protec their service and your own account.
base code from: Tile downloader https://github.com/fistulareffigy/MTD-Script/blob/main/TileDL.py
'''

map_style = None

# API Key and output directory
api_key = environ.get("API_KEY", None)

output_dir = environ.get("DOWNLOAD_DIRECTORY", join_path(expanduser("~"), "Desktop", "maps"))
os.makedirs(output_dir, exist_ok=True)


class MeshtasticTileDownloader:
    def __init__(self, output_directory: str):
        self.config = None
        self.output_directory = output_directory
        if not self.get_config():
            logging.critical("Configuration was not properly obtained from file.")

    @property
    def tile_provider(self):
        return self.config['map']['provider']

    @property
    def map_style(self):
        return self.config.get("map").get("style")

    @property
    def api_key(self):
        return self.config['api_key']

    @api_key.setter
    def api_key(self, key):
        self.config['api_key'] = key

    @property
    def zones(self):
        return [x for x in self.config['zones']]

    def get_config(self, config_file: str = "config.yaml"):
        self.config = safe_load(open(config_file, "r", encoding="utf-8"))
        return self.config

    def fix_config(self):
        logging.info("Analysing configuration.")
        try:
            fixing_zone = self.config['zones']
            logging.info(f"Found {len(fixing_zone)} zones")
            for zone in fixing_zone:
                regions = fixing_zone[zone]['regions']
                logging.info(f"[{zone}] contains {len(regions)} regions")
                if 'zoom' not in fixing_zone[zone]:
                    logging.warning("no zoom defined. will set to default zoom")
                    fixing_zone[zone]['zoom'] = {}
                if 'in' not in fixing_zone[zone]['zoom']:
                    fixing_zone[zone]['zoom']['in'] = 8
                if 'out' not in fixing_zone[zone]['zoom']:
                    fixing_zone[zone]['zoom']['out'] = 1
            if 'map' not in self.config:
                self.config['map'] = {
                    'provider': "thunderforest",
                    'style': "atlas"
                }
            if 'provider' not in self.config['map']:
                self.config['map']['provider'] = "thunderforest"
            if 'style' not in self.config['map']:
                self.config['map']['style'] = "atlas"

        except KeyError as e:
            logging.error(f"Error found on config. key not found: {e}")
            return False
        finally:
            return True

    @staticmethod
    def in_debug_mode():
        return environ.get("DEBUG", "false")

    @staticmethod
    def long_to_tile_x(lon, zoom):
        xy_tiles_count = 2 ** zoom
        return int(((lon + 180.0) / 360.0) * xy_tiles_count)

    @staticmethod
    def lat_to_tile_y(lat, zoom):
        xy_tiles_count = 2 ** zoom
        return int(((1.0 - log(tan(radians(lat)) + 1.0 / cos(radians(lat))) / pi) / 2.0) * xy_tiles_count)

    def parse_url(self, zoom: int, x: int, y: int):
        if self.tile_provider == "thunderforest":
            return f"https://tile.thunderforest.com/{self.map_style}/{zoom}/{x}/{y}.png?apikey={self.api_key}"
        elif self.tile_provider == "geoapify":
            return f"https://maps.geoapify.com/v1/tile/{self.map_style}/{zoom}/{x}/{y}.png?apiKey={self.api_key}"

    def redact_key(self, url: str):
        return url.replace(self.api_key, '[REDACTED]')

    def download_tile(self, zoom, x, y):
        url = self.parse_url(zoom, x, y)
        tile_dir = os.path.join(self.output_directory, self.tile_provider, self.map_style, str(zoom), str(x))
        tile_path = os.path.join(tile_dir, f"{y}.png")
        os.makedirs(tile_dir, exist_ok=True)
        redacted_url = self.redact_key(url)
        if self.in_debug_mode().lower() != "false":
            url = redacted_url
            logging.warning(f"DEBUG IS ACTIVE: not obtaining tile: {url}")
            return False
        if not os.path.exists(tile_path):
            response = requests.get(url)
            if response.status_code == 200:
                with open(tile_path, "wb") as file:
                    file.write(response.content)
            else:
                logging.error(f"Failed to download tile {zoom}/{x}/{y}: {response.status_code} {response.reason}")
        else:

            logging.info(f"[{tile_path}] file already exists. Skipping... {redacted_url}")

    # renamed from main
    def obtain_tiles(self, regions: list, zoom_levels: range):
        total_tiles = 0
        for zoom in zoom_levels:
            for region in regions:
                min_lat, min_lon, max_lat, max_lon = list(map(float, region.split(",")))
                start_x = self.long_to_tile_x(min_lon, zoom)
                end_x = self.long_to_tile_x(max_lon, zoom)
                start_y = self.lat_to_tile_y(max_lat, zoom)
                end_y = self.lat_to_tile_y(min_lat, zoom)

                total_tiles += abs((end_x - start_x + 1) * (end_y - start_y + 1))

        with tqdm(total=total_tiles, desc="Downloading tiles") as pbar:
            for zoom in zoom_levels:
                for region in regions:
                    min_lat, min_lon, max_lat, max_lon = list(map(float, region.split(",")))
                    start_x = self.long_to_tile_x(min_lon, zoom)
                    end_x = self.long_to_tile_x(max_lon, zoom)
                    start_y = self.lat_to_tile_y(max_lat, zoom)
                    end_y = self.lat_to_tile_y(min_lat, zoom)

                    for x in range(min(start_x, end_x), max(start_x, end_x) + 1):
                        for y in range(min(start_y, end_y), max(start_y, end_y) + 1):
                            self.download_tile(zoom=zoom, x=x, y=y)
                            pbar.update(1)

    def run(self):
        processing_zone = self.config['zones']
        for zone in processing_zone:
            regions = processing_zone[zone]['regions']
            zoom_out = processing_zone[zone]['zoom']['out']
            zoom_in = processing_zone[zone]['zoom']['in']
            zoom_levels = range(zoom_out, zoom_in +1)
            logging.info(f"Obtaining zone [{zone}] [zoom: {zoom_out} → {zoom_in}] regions: {regions}")
            self.obtain_tiles(regions=regions, zoom_levels=zoom_levels)
            logging.info(f"Finished with zone {zone}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.info(f"Store destination set at: {output_dir}")
    app = MeshtasticTileDownloader(output_directory=output_dir)

    if not app.fix_config():
        logging.critical("Configuration is not valid.")
        exit(1)

    if not api_key:
        logging.critical("No API_KEY found for downloading. It is expected as environment var API_KEY")
        exit(1)
    app.api_key = api_key
    del api_key

    app.run()

    zones = ",".join(app.zones)
    logging.info(f"Finished processing zones: {zones}")
    logging.info("Program finished")
    exit(0)