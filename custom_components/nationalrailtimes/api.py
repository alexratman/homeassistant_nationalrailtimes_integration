"""API wrapper for generating the XML envelope and fetching data from the Darwin API"""
import aiohttp
import async_timeout

from .apidata import ApiData


class Api:
    """API wrapper for generating the XML envelope and fetching data from the Darwin API"""

    def __init__(self, api_key, station, ):
        self.api_key = api_key
        self.time_offset = 0
        self.time_window = 120
        self.station = station
        self.destination = destination
        self.data = ApiData()

    def set_config(self, key, val):
        """Set config item, such as time_offset and time_window"""
        if key == "time_offset":
            self.time_offset = val
            return True

        if key == "time_window":
            self.time_window = val
            return True

    # def generate_filter_list(self):
    #     """Generate XML Destination Filters"""
    #     stations = self.filters
    #     payload = ""

    #     for station in stations:
    #         if station is not None:
    #             payload += f"<ldb:crs>{station}</ldb:crs>\n"

    #     return payload

    async def api_request(self):
        """
        To minimise multiple API calls, check if a request from another entity in this component is already in progress.
        If no request is running, generate SOAP Envelope and submit request to Darwin API.
        Otherwise, wait until the existing one is complete, and return that value.
        """
        url=f"https://api1.raildata.org.uk/1010-live-departure-board-dep/LDBWS/api/20220120/GetDepBoardWithDetails/{self.station}?numRows=5"
        return await self.request(self.url, aiohttp.get)

    async def fetch(self, session:aiohttp.ClientSession, url, params: dict):
        """Fetch data from the Darwin API"""
        try:
            with async_timeout.timeout(15):
                async with session.get(
                    url,
                    headers={
                        "Content-Type": "text/xml",
                        "charset": "utf-8",
                        "x-apikey": self.api_key
                    },
                    params=params
                ) as response:
                    result = await response.json()
                    return result
        except:
            pass

    async def request(self, url):
        """Prepare core request"""
        data={}
        if self.destination!=None:
            data["filterCrs"]=self.destination
            data["filterType"]="to"
        async with aiohttp.ClientSession() as session:
            return await self.fetch(session, url, data)
