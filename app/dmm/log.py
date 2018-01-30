import logging

LOG_LEVEL = logging.INFO
LOG_FILE = 'eo-dmm.log'

FORMAT_FIELD_SEP = ' '
FORMAT = '%(asctime)s{0}%(name)s{0}%(levelname)s{0}%(message)s'.format(FORMAT_FIELD_SEP)
FORMAT_DATE = '%Y-%m-%dT%H:%M:%SZ'


def get_logger(name=__name__, log_level=LOG_LEVEL):
    logging.basicConfig(filename=LOG_FILE, format=FORMAT,
                        datefmt=FORMAT_DATE, level=log_level)
    logger = logging.getLogger(name)
    return logger


class Logger(object):
    def __init__(self):
        self.log = get_logger('%s.%s' % (__name__, self.__class__.__name__))
