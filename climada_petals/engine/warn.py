"""
This file is part of CLIMADA.

Copyright (C) 2017 ETH Zurich, CLIMADA contributors listed in AUTHORS.

CLIMADA is free software: you can redistribute it and/or modify it under the
terms of the GNU General Public License as published by the Free
Software Foundation, version 3.

CLIMADA is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE.  See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along
with CLIMADA. If not, see <https://www.gnu.org/licenses/>.

---

Define the Warn class.
"""
import logging
import copy
from dataclasses import dataclass, field
from enum import Enum

from typing import List
from matplotlib.colors import ListedColormap
import numpy as np
import xarray as xr
import skimage

from climada.util.plot import geo_scatter_categorical

LOGGER = logging.getLogger(__name__)


def dilation(bin_map, size):
    """Dilate binary input map. The operation is based on a convolution. During translation of the
    filter, a point is included to the region (changed or kept to 1), if one or more elements
    correspond with the filter. Else, it is 0. This results in more and larger regions of
    interest. Larger filter sizes - more area of interest.

    Parameters
    ----------
    bin_map : np.ndarray
        Rectangle 2d map of values which are used to generate the warning.
    size : int
        Size of filter.

    Returns
    ----------
    np.ndarray
        Generated binary map with enlarged regions of interest.
    """
    return skimage.morphology.dilation(bin_map, skimage.morphology.disk(size))


def erosion(bin_map, size):
    """Erode binary input map. The operation is based on a convolution. During translation of the
    filter, a point is included to the region (changed or kept to 1), if all elements correspond
    with the filter. Else, it is 0. This results in less and smaller regions of interest and
    reduces heterogeneity in map. Larger sizes - more reduction.

    Parameters
    ----------
    bin_map : np.ndarray
        Rectangle 2d map of values which are used to generate the warning.
    size : int
        Size of filter.

    Returns
    ----------
    np.ndarray
        Generated binary map with reduced regions of interest.
    """
    return skimage.morphology.erosion(bin_map, skimage.morphology.disk(size))


def median_filtering(bin_map, size):
    """Smooth binary input map. The operation is based on a convolution. During translation of
    the filter, a point is included to the region (changed or kept to 1), if the median of the
    filter is 1. Else, it is 0. This results in smoother regions of interest and reduces
    heterogeneity in map. Larger sizes - smoother regions.

    Parameters
    ----------
    bin_map : np.ndarray
        Rectangle 2d map of values which are used to generate the warning.
    size : int
        Size of filter.

    Returns
    ----------
    np.ndarray
        Generated binary map with smoothed regions of interest.
    """
    return skimage.filters.median(bin_map, np.ones((size, size)))


class Operation(Enum):
    """Available Operations. Links operations to functions. More operations can be added.

    Attributes
    ----------
    dilation : function
        Links to dilation operation.
    erosion : function
        Links to erosion operation.
    median_filtering : function
        Links to median filtering operation.
    """
    dilation = dilation
    erosion = erosion
    median_filtering = median_filtering

    def __call__(self, *args, **kwargs):
        return self.value(*args, **kwargs)


class Warn:
    """Warn definition. Generate a warning, i.e., 2D map of coordinates with assigned warn levels.
    Operations, their order, and their influence (filter sizes) can be selected to generate the
    warning. Further properties can be chosen which define the warning generation. The
    functionality of reducing heterogeneity in a map can be applied to different inputs,
    e.g. MeteoSwiss windstorm data (COSMO data), TCs, impacts, etc.

    Attributes
    ----------
    warning : np.ndarray
        Warning generated by warning generation algorithm. Warn level for every coordinate of map.
    coord : np.ndarray
        Coordinates of warning map.
    warn_levels : list
        Warn levels that define the bins in which the input_map will be classified in.
        E.g., for windspeeds: [0, 10, 40, 80, 150, 200.0]
    """

    @dataclass
    class WarnParameters:
        """WarnParameters data class definition. It stores the relevant information needed during
        the warning generation. The operations and its sizes, as well as the algorithms
        properties $(gradual decrease of warning levels and changing of small warning regions
        formed) are saved.

        Attributes
        ----------
        warn_levels : list
            Warn levels that define the bins in which the input_map will be classified in.
        operations : list
            Tuples saving operations and their filter sizes to be applied in filtering algorithm.
        gradual_decr : bool
            Defines whether the highest warn levels should be gradually decreased by its neighboring
            regions (if True) to the lowest level (e.g., level 3, 2, 1, 0)
            or larger steps are allowed (e.g., from warn level 5 directly to 1).
        change_sm : int
            If strictly larger than 1, the levels of too small regions are changed to its
            surrounding levels. If 0 or None, the levels are not changed.
        """
        # default values for warning generation
        OPERATIONS = [('dilation', 2), ('erosion', 3), ('dilation', 7), ('median_filtering', 15)]
        GRADUAL_DECREASE = False
        CHANGE_SMALL_REGIONS = None

        warn_levels: List
        operations: List[str] = field(default_factory=lambda op=OPERATIONS: op)
        gradual_decr: bool = GRADUAL_DECREASE
        change_sm: bool = CHANGE_SMALL_REGIONS

        def __post_init__(self):
            op = [i[0] for i in self.operations]
            if not all(item in Operation.__dict__ for item in op):
                raise ValueError("An input operation is not defined. "
                                 "Please select only defined operations.")

    def __init__(self, warning, coord, warn_params):
        """Initialize Warn.

        Parameters
        ----------
        warning : np.ndarray
            Warn level for every coordinate of input map.
        coord : np.ndarray
            Coordinates of warning map.
        warn_params : dataclass
            Contains information on how to generate the warning (operations and details).
        """
        self.warning = warning
        self.coord = coord
        self.warn_params = warn_params

    @classmethod
    def from_map(cls, input_map, coord, warn_params):
        """Generate Warn object from map (value (e.g., windspeeds at coordinates).

        Parameters
        ----------
        input_map : np.ndarray
            Rectangle 2d map of values which are used to generate the warning.
        coord : np.ndarray
            Coordinates of warning map. For every value of the map exactly one coordinate is needed.
        warn_params : dataclass
            Contains information on how to generate the warning (operations and details).

        Returns
        ----------
        warn : Warn
            Generated Warn object including warning, coordinates, warn levels, and metadata.
        """
        if len(input_map.flatten()) != coord.shape[0]:
            raise Exception('For every coordinate a value in the map, and vice versa, is needed.')

        binned_map = cls.bin_map(input_map, warn_params.warn_levels)
        warning = cls._generate_warn_map(binned_map, warn_params)
        if warn_params.change_sm:
            warning = cls._change_small_regions(warning, warn_params.change_sm)
        return cls(warning, coord, warn_params)

    @classmethod
    def wind_from_cosmo(cls, path_to_cosmo, warn_params, lead_time, quant_nr=0.7):
        """Generate Warn object from COSMO windspeed data. The warn object is computed for the
        given date and time. The ensemble members of that date and time are grouped together to a
        single windspeed map.

        Parameters
        ----------
        path_to_cosmo : string
            Path including name to cosmo file.
        warn_params : dataclass
            Contains information on how to generate the warning (operations and details).
        lead_time : datetime
            Lead time when warning should be generated.
        quant_nr : float
            Quantile number to group ensemble members of COSMO wind speeds.

        Returns
        ----------
        warn : Warn
            Generated Warn object including warning, coordinates, warn levels, and metadata.
        """
        ncdf = xr.open_dataset(path_to_cosmo)
        ncdf = ncdf.sel(time=lead_time.strftime('%Y-%m-%dT%H'))
        ncdf = ncdf.drop('grid_mapping_1')

        lon = ncdf.lon_1.values
        lat = ncdf.lat_1.values
        coord = np.vstack((lat.flatten(), lon.flatten())).transpose()

        input_map = cls._group_cosmo_ensembles(ncdf.VMAX_10M, quant_nr)

        binned_map = cls.bin_map(input_map, warn_params.warn_levels)
        warning = cls._generate_warn_map(binned_map, warn_params)
        if warn_params.change_sm:
            warning = cls._change_small_regions(warning, warn_params.change_sm)
        return cls(warning, coord, warn_params)

    @staticmethod
    def bin_map(input_map, levels):
        """Bin every value of input map into given levels.

        Parameters
        ----------
        input_map : np.ndarray
            Array containing data to generate binned map of.
        levels : list
            List with levels to bin input map.

        Returns
        ----------
        binned_map : np.ndarray
            Map of binned values in levels, same shape as input map.
        """
        if np.min(input_map) < np.min(levels):
            LOGGER.warning('Values of input map are smaller than defined levels. '
                           'The smaller levels are set to the minimum level.')
        if np.max(input_map) > np.max(levels):
            LOGGER.warning('Values of input map are larger than defined levels. '
                           'The larger values are set to a new and higher warn level.')
        return np.digitize(input_map, levels) - 1  # digitize lowest bin is 1

    @staticmethod
    def _filtering(binary_map, warn_params):
        """For the current warn level, apply defined operations on the input binary map.

        Parameters
        ----------
        binary_map : np.ndarray
            Binary 2D array, where 1 corresponds to current (and higher if grad_decrease) level.
        warn_params : dataclass
            Contains information on how to generate the warning (operations and details).

        Returns
        ----------
        binary_curr_lvl : np.ndarray
            Warning map consisting formed warning regions of current warn level.
        """
        for op, sz in warn_params.operations:
            binary_map = Operation.__dict__[op](binary_map, sz)

        return binary_map

    @staticmethod
    def _generate_warn_map(bin_map, warn_params):
        """Generate warning map of binned map. The filter algorithm reduces heterogeneity in the map
        (erosion) and makes sure warn regions of higher warn levels are large enough (dilation).
        With the median filtering the generated warning is smoothed out without blurring.

        Parameters
        ----------
        bin_map : np.ndarray
            Map of binned values in warn levels. Hereof a warning with contiguous regions is formed.
        warn_params : dataclass
            Contains information on how to generate the warning (operations and details).

        Returns
        ----------
        warn_regions : np.ndarray
            Warning map consisting formed warning regions, same shape as input map.
        """
        max_warn_level = np.max(bin_map)
        min_warn_level = np.min(bin_map)

        warn_map = np.zeros_like(bin_map) + min_warn_level
        for curr_lvl in range(max_warn_level, min_warn_level, -1):
            if warn_params.gradual_decr:
                pts_curr_lvl = np.bitwise_or(warn_map > curr_lvl, bin_map >= curr_lvl)
            else:
                pts_curr_lvl = bin_map == curr_lvl
            # set bool np.ndarray to curr_lvl (if True) or 0
            binary_curr_lvl = np.where(pts_curr_lvl, curr_lvl, 0)

            warn_reg = Warn._filtering(binary_curr_lvl, warn_params)
            # keep warn regions of higher levels by taking maximum
            warn_map = np.maximum(warn_map, warn_reg)

        return warn_map

    @staticmethod
    def _increase_levels(warn, size):
        """Increase warn levels of too small regions to max warn level of this warning.

        Parameters
        ----------
        warn : np.ndarray
            Warning map of which too small regions are changed to surrounding. Levels are +1.
        size : int
            Threshold defining too small regions (number of coordinates).

        Returns
        ----------
        warn : np.ndarray
            Warning map where too small regions are of the higher level occurring. Levels are +1.
        """
        labels = skimage.measure.label(warn)
        for l in np.unique(labels):
            cnt = np.count_nonzero(labels == l)
            if cnt <= size:
                warn[labels == l] = np.max(warn, axis=(0, 1))
        return warn

    @staticmethod
    def _reset_levels(warn, size):
        """Set warn levels of too small regions to highest surrounding warn level. Therefore,
        decrease warn levels of too small regions, until no too small regions can be detected.

        Parameters
        ----------
        warn : np.ndarray
            Warning map of which too small regions are changed to surrounding. Levels are +1.
        size : int
            Threshold defining too small regions (number of coordinates).

        Returns
        ----------
        warn : np.ndarray
            Warning map where too small regions are changed to neighborhood. Warn levels are all +1.
        """
        for i in range(np.max(warn), np.min(warn), -1):
            level = copy.deepcopy(warn)
            level[warn != i] = 0
            labels = skimage.measure.label(warn)
            for l in np.unique(labels):
                cnt = np.count_nonzero(labels == l)
                if cnt <= size:
                    warn[labels == l] = i - 1
        return warn

    @staticmethod
    def _change_small_regions(warning, size):
        """Change formed warning regions smaller than defined threshold from current warn level to
        surrounding warn level.

        Parameters
        ----------
        warning : np.ndarray
            Warning map of which too small regions are changed to surrounding.
        size : int
            Threshold defining too small regions (number of coordinates).

        Returns
        ----------
        warning : np.ndarray
            Warning without too small regions, same shape as input map.
        """
        warning = warning + 1  # 0 is regarded as background in labelling, + 1 prevents this
        warning = Warn._increase_levels(warning, size)
        warning = Warn._reset_levels(warning, size)
        warning = warning - 1
        return warning

    @staticmethod
    def _group_cosmo_ensembles(ensembles, quant_nr):
        """The ensemble members of the COSMO computations are grouped together by taking the
        given quantile.

        Parameters
        ----------
        ensembles : np.ndarray
            Wind speed data by COSMO. Multiple possible outcomes for every grid point (ensemble
            members).
        quant_nr : float
            Quantile number to group ensemble members of COSMO wind speeds.

        Returns
        ----------
        single_map : np.ndarray
            Map with one wind speed for every grid point (reduced dimension compared to input).
        """
        single_map = np.quantile(ensembles, quant_nr, axis=0)
        return single_map

    def plot_warning(self, var_name='Warn Levels', title='Categorical Warning Map', cat_name=None,
                     adapt_fontsize=True,
                     **kwargs):
        """
        Map plots for categorical data defined in array(s) over input
        coordinates. The categories must be a finite set of unique values
        as can be identified by np.unique() (mix of int, float, strings, ...).

        The categories are shared among all subplots, i.e. are obtained from
        np.unique(array_sub).
        Eg.:
            array_sub = [[1, 2, 1.0, 2], [1, 2, 'a', 'a']]
            -> categories mapping is [[0, 2, 1, 2], [0, 2, 3, 3]]

        Same category: 1 and '1'
        Different categories: 1 and 1.0

        This method wraps around util.geo_scatter_from_array and uses
        all its args and kwargs.

        Parameters
        ----------
        var_name : str or list(str)
            label to be shown in the colorbar. If one
            provided, the same is used for all subplots. Otherwise provide as
            many as subplots in array_sub.
        title : str or list(str)
            subplot title. If one provided, the same is
            used for all subplots. Otherwise provide as many as subplots in
            array_sub.
        cat_name : dict, optional
            Categories name for the colorbar labels.
            Keys are all the unique values in array_sub, values are their labels.
            The default is labels = unique values.
        adapt_fontsize : bool, optional
            If set to true, the size of the fonts will be adapted to the size of the figure.
            Otherwise the default matplotlib font size is used. Default is True.
        **kwargs
            Arbitrary keyword arguments for hexbin matplotlib function

        Returns
        -------
        cartopy.mpl.geoaxes.GeoAxesSubplot

        """
        return geo_scatter_categorical(self.warning.flatten(), self.coord, var_name, title,
                                       cat_name, adapt_fontsize,
                                       **kwargs)

    def plot_warning_meteoswiss_style(self, var_name='Warn Levels', title='Categorical Warning '
                                                                          'Map', cat_name=None,
                                      adapt_fontsize=True):
        """
        Map plots for categorical data defined in array(s) over input
        coordinates. The MeteoSwiss coloring scheme is used, therefore only 5 warn levels are
        allowed.

        This method wraps around util.geo_scatter_from_array and uses
        all its args and kwargs.

        Parameters
        ----------
        var_name : str or list(str)
            label to be shown in the colorbar. If one
            provided, the same is used for all subplots. Otherwise provide as
            many as subplots in array_sub.
        title : str or list(str)
            subplot title. If one provided, the same is
            used for all subplots. Otherwise provide as many as subplots in
            array_sub.
        cat_name : dict, optional
            Categories name for the colorbar labels.
            Keys are all the unique values in array_sub, values are their labels.
            The default is labels = unique values.
        adapt_fontsize : bool, optional
            If set to true, the size of the fonts will be adapted to the size of the figure.
            Otherwise the default matplotlib font size is used. Default is True.
        **kwargs
            Arbitrary keyword arguments for hexbin matplotlib function

        Returns
        -------
        cartopy.mpl.geoaxes.GeoAxesSubplot

        """
        if np.max(self.warning) > 4:
            raise ValueError("MeteoSwiss defines only 5 warn levels. You used more levels or the "
                             "values of input map are larger than defined levels. Reduce "
                             "the number of warn levels to 5 or use 'plot_warning() instead.")

        colors_mch = np.array([[204 / 255, 255 / 255, 102 / 255, 1],  # green
                               [255 / 255, 255 / 255, 0 / 255, 1],  # yellow
                               [255 / 255, 153 / 255, 0 / 255, 1],  # orange
                               [255 / 255, 0 / 255, 0 / 255, 1],  # red
                               [128 / 255, 0 / 255, 0 / 255, 1],  # dark red
                               ])
        newcmp = ListedColormap(colors_mch)
        kwargs = dict()
        kwargs['cmap'] = newcmp

        return geo_scatter_categorical(self.warning.flatten(), self.coord, var_name, title,
                                       cat_name, adapt_fontsize,
                                       **kwargs)
