import os

from chimera.core import SYSTEM_CONFIG_DIRECTORY
from sqlalchemy import (Column, String, Integer, DateTime, Float, MetaData, create_engine)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DB_FILE = os.path.join(SYSTEM_CONFIG_DIRECTORY, 'image_statistics.db')
engine = create_engine('sqlite:///%s' % DB_FILE, echo=False)
metaData = MetaData()
metaData.bind = engine

Session = sessionmaker(bind=engine)
Base = declarative_base(metadata=metaData)


class ImageStatistics(Base):
    __tablename__ = "image_statistics"

    id = Column(Integer, primary_key=True)
    filename = Column(String, default="")
    date_obs = Column(DateTime, default=None)
    fwhm_avg = Column(Float, default=None)
    fwhm_std = Column(Float, default=None)
    background = Column(Float, default=None)
    npts = Column(Integer, default=None)

    # def __str__ (self):
    #     if self.observed:
    #         return "#%d %s [type: %s] #LastObverved@: %s" % (self.id, self.name, self.type,
    #                                                     self.lastObservation)
    #     else:
    #         return "#%d %s [type: %s] #NeverObserved" % (self.id, self.name, self.type)


metaData.create_all(engine)
