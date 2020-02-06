#!/usr/bin/env python3 -u
# coding: utf-8

__all__ = ["DummyForecaster"]
__author__ = "Markus Löning"

from warnings import warn

import numpy as np
import pandas as pd

from sktime.forecasting.base import _BaseForecasterOptionalFHinFit, DEFAULT_ALPHA
from sktime.utils.validation.forecasting import validate_y
from sktime.utils.validation.forecasting import validate_sp
from sktime.utils.validation.forecasting import validate_window_length
from sktime.forecasting.model_selection import SlidingWindowSplitter


class DummyForecaster(_BaseForecasterOptionalFHinFit):
    """
    NaiveForecaster is a forecaster that makes forecasts using simple strategies.

    Parameters
    ----------
    strategy : str, {"last", "mean", "seasonal_last"}, optional (default="last")
        Strategy used to make forecasts:

        * "last": forecast the last value in the training series
        * "mean": forecast the mean of (a given window) of the training series

    window_length : int or None, optional (default=None)
        Window length to use in the `mean` strategy. If None, entire training
            series will be used.
    """

    def __init__(self, strategy="last", window_length=None, sp=None):

        # input checks
        # allowed strategies to include: last, constant, seasonal-last, mean, median
        allowed_strategies = ("last", "mean", "seasonal_last")
        if strategy not in allowed_strategies:
            raise ValueError(f"Unknown strategy: {strategy}; expected one of {allowed_strategies}")
        self.strategy = strategy
        self.window_length = window_length
        self.sp = sp

        if self.strategy in ("last", "seasonal_last"):
            if window_length is not None:
                warn("For the `last` and `seasonal_last` strategy, "
                     "the `window_length` value will be ignored.")

        if self.strategy in ("last", "mean"):
            if sp is not None:
                warn("For the `last` and `mean` strategy, "
                     "the `sp` value will be ignored.")

        if self.strategy == "last":
            self._window_length = 1

        if self.strategy == "seasonal_last":
            if sp is None:
                raise NotImplementedError("Automatic estimation of the seasonal periodicity `sp` "
                                          "from the data is not implemented yet; "
                                          "please specify the `sp` value.")
            sp = validate_sp(sp)
            self._window_length = sp
            self._sp = sp

        if self.strategy == "mean":
            self._window_length = validate_window_length(window_length)

        self._last_window = None
        self._first_window = None
        super(DummyForecaster, self).__init__()

    def fit(self, y, fh=None):
        """Fit"""

        y = validate_y(y)
        self._set_fh(fh)

        # update observation horizon
        self._set_obs_horizon(y.index)

        # set default window length for the mean strategy
        if self.strategy == "mean" and self._window_length is None:
            self._window_length = len(y)

        if self._window_length > len(self._obs_horizon):
            param = "sp" if self.strategy == "seasonal_last" else "window_length"
            raise ValueError(f"The {param}: {self._window_length} is larger than "
                             f"the training series.")

        self._first_window = y.iloc[:self._window_length]
        self._last_window = y.iloc[-self._window_length:]

        self._is_fitted = True
        return self

    def predict(self, fh=None, return_pred_int=False, alpha=DEFAULT_ALPHA):
        """Predict"""

        # input checks
        if return_pred_int:
            raise NotImplementedError()

        self._check_is_fitted()
        self._set_fh(fh)

        # compute prediction
        if self.strategy == "last":
            y_pred = np.repeat(self._last_window.iloc[-1], len(self.fh))

        if self.strategy == "seasonal_last":
            # we need to replicate the last window if max(fh) is larger than sp,
            # so that we still make forecasts by repeating the last value for that season,
            # assume fh is sorted, i.e. max(fh) == fh[-1]
            if self.fh[-1] > self.sp:
                reps = np.int(np.ceil(self.fh[-1] / self.sp))
                last_window = np.tile(self._last_window, reps=reps)
            else:
                last_window = self._last_window.values

            fh_idx = self.fh - np.min(self.fh)
            y_pred = last_window[fh_idx]

        if self.strategy == "mean":
            y_pred = np.repeat(self._last_window.mean(), len(self.fh))

        # return as series with correct time index
        index = self._now + self.fh
        return pd.Series(y_pred, index=index)

    def update(self, y_new, update_params=False):
        """Update"""

        # input checks
        self._check_is_fitted()
        y_new = validate_y(y_new)

        # update observation horizon
        self._set_obs_horizon(y_new.index)

        # update windows
        self._last_window = self._last_window.append(y_new).iloc[-self._window_length:]
        return self

    def predict_in_sample(self, y_train, return_pred_int=False, alpha=DEFAULT_ALPHA):
        """Make in-sample predictions"""

        y_train = validate_y(y_train)
        window_length = self._window_length

        n_timepoints = len(y_train)
        y_pred = np.zeros(n_timepoints)

        y_pred[:window_length] = np.nan

        self._last_window = y_train[:window_length]

        cv = SlidingWindowSplitter(fh=1, window_length=window_length)
        for k, (i, o) in enumerate(cv.split(y_train.index), start=window_length):
            y_new = y_train.iloc[i]
            self._last_window = self._last_window.append(y_new).iloc[-self._window_length:]
            y_pred[k] = self.predict(fh=1, return_pred_int=return_pred_int, alpha=alpha)

        return pd.Series(y_pred, index=y_train.index)


