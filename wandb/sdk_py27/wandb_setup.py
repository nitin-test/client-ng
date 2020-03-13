"""
setup.
"""

import threading
import multiprocessing
import sys
import os
import datetime
import errno
import logging
import copy
import os

from . import wandb_settings

logger = logging.getLogger("wandb")


class _EarlyLogger(object):
    def __init__(self):
        self._log = []
        self._exception = []

    def debug(self, msg, *args, **kwargs):
        self._log.append((logging.DEBUG, msg, args, kwargs))

    def info(self, msg, *args, **kwargs):
        self._log.append((logging.INFO, msg, args, kwargs))

    def warning(self, msg, *args, **kwargs):
        self._log.append((logging.WARNING, msg, args, kwargs))

    def error(self, msg, *args, **kwargs):
        self._log.append((logging.ERROR, msg, args, kwargs))

    def critical(self, msg, *args, **kwargs):
        self._log.append((logging.CRITICAL, msg, args, kwargs))

    def exception(self, msg, *args, **kwargs):
        self._exception.append(msg, args, kwargs)

    def log(self, level, msg, *args, **kwargs):
        self._log.append(level, msg, args, kwargs)

    def _flush(self):
        for level, msg, args, kwargs in self._log:
            logger.log(level, msg, *args, **kwargs)
        for msg, args, kwargs in self._exception:
            logger.exception(msg, *args, **kwargs)


class _WandbSetup__WandbSetup(object):
    """Inner class of _WandbSetup."""
    def __init__(self, settings=None, environ=None):
        self._multiprocessing = None
        self._settings = None
        self._environ = environ or os.environ
        self._log_user_filename = None
        self._log_internal_filename = None
        self._data_filename = None
        self._log_dir = None
        self._filename_template = None

        # TODO(jhr): defer strict checks until settings is fully initialized and logging is ready
        early_logging = _EarlyLogger()
        self._settings_setup(settings, early_logging)
        self._log_setup()
        self._settings_early_flush(early_logging)
        early_logging = None

        self._check()
        self._setup()

    def _settings_setup(self, settings=None, early_logging=None):
        glob_config = os.path.expanduser('~/.config/wandb/settings')
        loc_config = 'wandb/settings'
        files = (glob_config, loc_config)
        s = wandb_settings.Settings(environ=self._environ,
                                    early_logging=early_logging,
                                    files=files)
        if settings:
            s.update(settings)
        s.freeze()
        self._settings = s

    def _settings_early_flush(self, early_logging):
        if early_logging:
            self._settings._clear_early_logging()
            early_logging._flush()

    def settings(self, __d=None, **kwargs):
        s = copy.copy(self._settings)
        s.update(__d, **kwargs)
        return s

    def _enable_logging(self, log_fname, run_id=None):
        """Enable logging to the global debug log.  This adds a run_id to the log,
        in case of muliple processes on the same machine.

        Currently no way to disable logging after it's enabled.
        """
        handler = logging.FileHandler(log_fname)
        handler.setLevel(logging.INFO)

        class WBFilter(logging.Filter):
            def filter(self, record):
                record.run_id = run_id
                return True

        if run_id:
            formatter = logging.Formatter(
                '%(asctime)s %(levelname)-7s %(threadName)-10s:%(process)d [%(run_id)s:%(filename)s:%(funcName)s():%(lineno)s] %(message)s'
            )
        else:
            formatter = logging.Formatter(
                '%(asctime)s %(levelname)-7s %(threadName)-10s:%(process)d [%(filename)s:%(funcName)s():%(lineno)s] %(message)s'
            )

        handler.setFormatter(formatter)
        if run_id:
            handler.addFilter(WBFilter())
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)

    def _log_setup(self):
        # log dir - where python logs go
        log_dir = "wandb"
        # log spec
        # TODO: read from settings
        log_user_spec = "wandb-{timespec}-{pid}-debug-user.txt"
        log_internal_spec = "wandb-{timespec}-{pid}-debug-internal.txt"
        # TODO(jhr): should we use utc?
        when = datetime.datetime.now()
        pid = os.getpid()
        datestr = datetime.datetime.strftime(when, "%Y%m%d_%H%M%S")
        d = dict(pid=pid, timespec=datestr)
        log_user = os.path.join(log_dir, log_user_spec.format(**d))
        log_internal = os.path.join(log_dir, log_internal_spec.format(**d))
        try:
            os.makedirs(log_dir)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise
        if not os.path.isdir(log_dir):
            raise Exception("not dir")
        if not os.access(log_dir, os.W_OK):
            raise Exception("cant write: {}".format(log_dir))
        #print("loguser", log_user)
        #print("loginternal", log_internal)
        self._enable_logging(log_user)

        logger.info("Logging to {}".format(log_user))
        self._filename_template = d
        self._log_user_filename = log_user
        self._log_internal_filename = log_internal
        self._log_dir = log_dir

    def _check(self):
        if hasattr(threading, "main_thread"):
            if threading.current_thread() is not threading.main_thread():
                print("bad thread")
        elif threading.current_thread().name != 'MainThread':
            print("bad thread2", threading.current_thread().name)
        if getattr(sys, 'frozen', False):
            print("frozen, could be trouble")
        #print("t2", multiprocessing.get_start_method(allow_none=True))
        #print("t3", multiprocessing.get_start_method())

    def _setup(self):
        #TODO: use fork context if unix and frozen?
        # if py34+, else fall back
        if hasattr(multiprocessing, "get_context"):
            all_methods = multiprocessing.get_all_start_methods()
            logger.info("multiprocessing start_methods={}".format(
                ','.join(all_methods)))
            ctx = multiprocessing.get_context('spawn')
        else:
            logger.info("multiprocessing fallback, likely fork on unix")
            ctx = multiprocessing
        self._multiprocessing = ctx
        #print("t3b", self._multiprocessing.get_start_method())

        self._data_filename = os.path.join(self._log_dir, self._settings.data_spec.format(**self._filename_template))

    def on_finish(self):
        logger.info("done")


class _WandbSetup(object):
    """Wandb singleton class."""
    _instance = None

    def __init__(self, settings=None):
        # TODO(jhr): what do we do if settings changed?
        if _WandbSetup._instance is not None:
            return
        _WandbSetup._instance = __WandbSetup(settings=settings)

    def __getattr__(self, name):
        return getattr(self._instance, name)


def setup(settings=None):
    """Setup library context."""
    wl = _WandbSetup(settings=settings)
    return wl