# Python AIM XRK file reader and parser.
#
# Wraps the "Matlab" xrk DLL provided by AIM from
# https://www.aim-sportline.com/download/software/doc/how-to-access-xrk-files-data-without-aim-software_101.pdf
#
# Copyright (c) 2023, Jacob Hill, (trapperrnz@gmail.com)
#

import bisect
from ctypes import *
import datetime
import functools
import os
import time
import textwrap

DLLNAME = os.path.join(os.path.dirname(__file__), 'MatLabXRK-2017-64-ReleaseU.dll')
XRKDLL = cdll.LoadLibrary(DLLNAME)

# Need to override the DLL function signatures for non-int return types
# awk '/EXPORTED_FUNCTION/ { if ($2 != "int") { print; }}' MatLabXRK.h 
XRKDLL.get_library_date.restype = c_char_p
XRKDLL.get_library_time.restype = c_char_p
XRKDLL.get_vehicle_name.restype = c_char_p
XRKDLL.get_track_name.restype = c_char_p
XRKDLL.get_racer_name.restype = c_char_p
XRKDLL.get_championship_name.restype = c_char_p
XRKDLL.get_venue_type_name.restype = c_char_p
class TimeStruct(Structure):
    _fields_ = [
        ("tm_sec", c_int),
        ("tm_min", c_int),
        ("tm_hour", c_int),
        ("tm_mday", c_int),
        ("tm_mon", c_int),
        ("tm_year", c_int),
        ("tm_wday", c_int),
        ("tm_yday", c_int),
        ("tm_isdst", c_int),
    ]
XRKDLL.get_date_and_time.restype = POINTER(TimeStruct)
XRKDLL.get_channel_name.restype = c_char_p
XRKDLL.get_channel_units.restype = c_char_p
XRKDLL.get_GPS_channel_name.restype = c_char_p
XRKDLL.get_GPS_channel_units.restype = c_char_p
XRKDLL.get_GPS_raw_channel_name.restype = c_char_p
XRKDLL.get_GPS_raw_channel_units.restype = c_char_p


# Data channel class
class XRKChannel():
    def __init__(self, name: str, idxf: int, idxc: int, xrk):
        self.name = name
        self.idxf = idxf
        self.idxc = idxc
        self.xrk = xrk
        self.f_get_channel_units = XRKDLL.get_channel_units
        self.f_get_channel_samples_count = XRKDLL.get_channel_samples_count
        self.f_get_channel_samples = XRKDLL.get_channel_samples
        self.f_get_lap_channel_samples_count = XRKDLL.get_lap_channel_samples_count
        self.f_get_lap_channel_samples = XRKDLL.get_lap_channel_samples

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}', idxf={self.idxf}, idxc={self.idxc})"

    def units(self):
        return self.f_get_channel_units(self.idxf, self.idxc).decode('UTF-8')

    def samples(self, lap: int=None, xtime: bool=False, xabsolute: bool=False):
        '''Returns data samples for a channel.
        Params:
            lap: if you want a specific lap, give the integer here (0 offset)
            xtime: xvalues in time in seconds (vs distance in meters)
            xasolute: is x absolute since the start of session, or relative?

        Returns:
            Data points in columnar format: [[xvalues, ], [values]]
        '''

        # This function is messy idk how to make it simpler; Putting the complexity here
        # contains it rather than sprinkling it around.
        #
        # Complexity dealt with in here:
        # . retrieve lap vs whole data file
        # . absolute or relative for the xvalues
        # . time vs distance for xvalues

        sample_count = self.f_get_channel_samples_count(self.idxf, self.idxc)
        if lap:
            sample_count=self.f_get_lap_channel_samples_count(self.idxf, lap, self.idxc)

        # going with assert here ... maybe a bad call and should handle this gracefully?
        assert(sample_count > 0), f"get samples_count returned something unexpected {sample_count}"

        ptimes = (c_double * sample_count)()
        pvalues = (c_double * sample_count)()

        success = None
        if lap:
            success = self.f_get_lap_channel_samples(self.idxf, lap, self.idxc,
                                                     byref(ptimes),
                                                     byref(pvalues),
                                                     sample_count)
        else:
            success = self.f_get_channel_samples(self.idxf, self.idxc, byref(ptimes), 
                                                 byref(pvalues), sample_count)

        # going with assert here ... maybe a bad call and should handle this gracefully?
        assert(success > 0), f"get_channel_samples returned something unexpected {success}"

        xvalues = [] # either times in seconds, or distance in meters
        samples = []
        for i in range(sample_count):
            # The timestamps for all samples are in milliseconds, but if
            # you ask for a lap's worth of samples with the lap function, it
            # comes back with time in seconds. This blob does the multiply
            # munge on the returned data.
            if not lap:
                ptime = round(ptimes[i]/1000.0, 4)
            else:
                ptime = round(ptimes[i], 4)
            # If dealing in distance instead of time, convert to distance here
            if not xtime:
                ptime = self.xrk.timetodistance(ptime)

            xvalues.append(ptime)
            samples.append(pvalues[i])

        # If not xabsolute, convert xvalues to relative by subtracting the start
        if not xabsolute and lap:
            # grab the lap start to subtract
            lap_start, lap_duration = self.xrk.lap_info[lap]
            # and if not dealing in time ... convert start to distance ;)
            if not xtime:
                lap_start = self.xrk.timetodistance(lap_start)

            xvalues = [x - lap_start for x in xvalues]

        return [xvalues, samples]


# Function pointer swizzles of generic XRKChannel
class XRKGPSChannel(XRKChannel):
    def __init__(self, name: str, idxf: int, idxc: int, xrk):
        super().__init__(name, idxf, idxc, xrk)
        self.f_get_channel_units = XRKDLL.get_GPS_channel_units
        self.f_get_channel_samples_count = XRKDLL.get_GPS_channel_samples_count
        self.f_get_channel_samples = XRKDLL.get_GPS_channel_samples
        self.f_get_lap_channel_samples_count = XRKDLL.get_lap_GPS_channel_samples_count
        self.f_get_lap_channel_samples = XRKDLL.get_lap_GPS_channel_samples


# Function pointer swizzles of generic XRKChannel
class XRKGPSrawChannel(XRKChannel):
    def __init__(self, name: str, idxf: int, idxc: int, xrk):
        super().__init__(name, idxf, idxc, xrk)
        self.f_get_channel_units = XRKDLL.get_GPS_raw_channel_units
        self.f_get_channel_samples_count = XRKDLL.get_GPS_raw_channel_samples_count
        self.f_get_channel_samples = XRKDLL.get_GPS_raw_channel_samples
        self.f_get_lap_channel_samples_count = XRKDLL.get_lap_GPS_raw_channel_samples_count
        self.f_get_lap_channel_samples = XRKDLL.get_lap_GPS_raw_channel_samples


class XRK():
    def __init__(self, filename: str):
        self.filename = filename
        fileptr = c_char_p(os.path.abspath(f'{filename}').encode())
        self.idxf = XRKDLL.open_file(fileptr.value)
        # everything hinges off of idxf...
        assert(self.idxf > 0)

    def close(self):
        return XRKDLL.close_file_i(self.idxf) > 0

    def __repr__(self):
        return (f"XRK(datetime={self.datetime}, lapcount={self.lapcount}, "
                f"vehicle_name={self.vehicle_name}, "
                f"track_name={self.track_name}, racer_name={self.racer_name}, "
                f"championship_name={self.championship_name})")


    def summary(self) -> str:
        text = [textwrap.dedent(f'''\
            Track: {self.track_name}
            Date: {self.datetime}
            Driver: {self.racer_name}
            Vehicle: {self.vehicle_name}
            Championship: {self.championship_name}
            Laps: {self.lapcount}
            '''),]
        for i in range(len(self.lap_info)):
            m, s = divmod(self.lap_info[i][1], 60)
            if i == self.bestlap:
                text.append(f'*{i}*\t*{m:.0f}:{s:.3f}*\n')
            else:
                text.append(f' {i} \t {m:.0f}:{s:.3f}\n')
        return ''.join(text)

    @functools.cached_property
    def bestlap(self) -> int:
        bestlap = 0
        for i in range(len(self.lap_info)):
            if self.lap_info[i][1] < self.lap_info[bestlap][1]:
                bestlap=i
        return bestlap

    @functools.cached_property
    def vehicle_name(self) -> str:
        return XRKDLL.get_vehicle_name(self.idxf).decode('UTF-8')

    @functools.cached_property
    def track_name(self) -> str:
        return XRKDLL.get_track_name(self.idxf).decode('UTF-8')

    @functools.cached_property
    def racer_name(self) -> str:
        return XRKDLL.get_racer_name(self.idxf).decode('UTF-8')

    @functools.cached_property
    def championship_name(self) -> str:
        return XRKDLL.get_championship_name(self.idxf).decode('UTF-8')

    @functools.cached_property
    def venue_type(self) -> str:
        return XRKDLL.get_venue_type_name(self.idxf).decode('UTF-8')

    @functools.cached_property
    def datetime(self) -> str:
        # returns a pointer, so we grab the 1st (only) one
        t = XRKDLL.get_date_and_time(self.idxf)[0]
        mktime = time.mktime((t.tm_year+1900, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min,
                           t.tm_sec, t.tm_wday, t.tm_yday, t.tm_isdst))
        return datetime.datetime.fromtimestamp(mktime).strftime("%Y-%m-%d %H:%M:%S")

    @functools.cached_property
    def lapcount(self) -> int:
        return XRKDLL.get_laps_count(self.idxf)

    @functools.cached_property
    def channels(self) -> dict:
        channels = {}
        for i in range(XRKDLL.get_channels_count(self.idxf)):
            name = XRKDLL.get_channel_name(self.idxf, i).decode('UTF-8')
            assert(name not in channels), "channel name collision!"
            channels[name] = XRKChannel(name, self.idxf, i, self)

        for i in range(XRKDLL.get_GPS_channels_count(self.idxf)):
            name = XRKDLL.get_GPS_channel_name(self.idxf, i).decode('UTF-8')
            assert(name not in channels), "channel name collision!"
            channels[name] = XRKGPSChannel(name, self.idxf, i, self)

        for i in range(XRKDLL.get_GPS_raw_channels_count(self.idxf)):
            name = XRKDLL.get_GPS_raw_channel_name(self.idxf, i).decode('UTF-8')
            assert(name not in channels), "channel name collision!"
            channels[name] = XRKGPSrawChannel(name, self.idxf, i, self)

        return channels

    @functools.cached_property
    def timedistance(self) -> 'tuple[list[int], list[int]]':
        '''Compute the time distance vector for the entire datafile using GPS
        Speed

        Returns:
            2 lists: absolute time, corresponding absolute distance
            [[time, ], [distance, ]]
        '''
        # XXX MUST set xabsolute and xtime or we recurse using the data we're calculating XXX
        seconds, speeds = self.channels['GPS Speed'].samples(xabsolute=True, xtime=True)
        assert(len(seconds) == len(speeds)) # paranoia

        # distance is in m/s
        distance = [0, ]
        totdistance = 0
        for i in range(1, len(seconds)):
            timedelta = seconds[i]-seconds[i-1]
            traveled = timedelta*speeds[i]
            totdistance = totdistance + traveled
            distance.insert(i, totdistance)

        return (seconds, distance)


    def _tdlookup(self, needle, haystack, cdata):
        '''Generic lookup for the timedistance pair of lists.

        This will find a point in one stream, and return the corresponding data
        point in the other, including interpolating when necessary.
        '''
        idx = bisect.bisect_left(haystack, needle)
        if idx >= len(haystack):
            return cdata[-1]
        elif haystack[idx] == needle:
            # easy, found the needle, just return the data
            return cdata[idx]
        else:
            # non-easy case, interpolate
            try:
                ratio = ((needle - haystack[idx]) / 
                         (haystack[idx+1] - haystack[idx]))
            except ZeroDivisionError:
                ratio = 1
            fudge = (cdata[idx+1] - cdata[idx]) * ratio
            return round(cdata[idx]+fudge, 4)

    def timetodistance(self, itime: float):
        '''Convert an absolute time (s) to absolute distance (m)'''
        times, distances = self.timedistance
        return self._tdlookup(itime, times, distances)

    def distancetotime(self, idistance: float):
        '''Convert an absolute distance (m) to absolute time (s)'''
        times, distances = self.timedistance
        return self._tdlookup(idistance, distances, times)

    @functools.cached_property
    def lap_info(self) -> 'list[tuple[float, float]]':
        pstart = c_double(0)
        pduration = c_double(0)

        data = []
        for i in range(self.lapcount):
            XRKDLL.get_lap_info(self.idxf, i, byref(pstart), byref(pduration))
            data.append((round(pstart.value, 4), round(pduration.value, 4)))

        return data
