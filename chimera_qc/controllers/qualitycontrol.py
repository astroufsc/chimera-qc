import time
import datetime
import json
import os
import threading
from tempfile import mktemp
import ntpath

import numpy as np
import requests
from chimera.core.callback import callback
from chimera.core.chimeraobject import ChimeraObject
from chimera.core.manager import Manager
from chimera.interfaces.camera import CameraStatus
from chimera.util.image import ImageUtil, Image
from chimera.controllers.imageserver.util import getImageServer
from chimera.core.exceptions import ChimeraException

from chimera_qc.controllers.model import Session, ImageStatistics


class QualityControl(ChimeraObject):
    __config__ = {
        "camera": "/Camera/0",
        "scheduler": "/Scheduler/0",
        "sex_params": None  # json file, PARAMETER_LIST is overriden
    }

    def _getCam(self):
        return self.getManager().getProxy(self["camera"])

    def getSched(self):
        return self.getManager().getProxy(self["scheduler"])

    def __init__(self):
        ChimeraObject.__init__(self)
        # self.stats = dict()

    def __start__(self):

        self.setHz(1 / 10.)

        # Load SEXtractor params
        if self["sex_params"] is not None:
            with open(os.path.expanduser(self["sex_params"])) as fp:
                self._sex_params = json.load(fp)
        else:
            self._sex_params = {}

        self._sex_params['PARAMETERS_LIST'] = ["NUMBER", "XWIN_IMAGE", "YWIN_IMAGE", "FLUX_BEST", "FWHM_IMAGE", "FLAGS",
                                               "CLASS_STAR", "BACKGROUND"]

        # self._data = dict()
        # self.sched_callbacks = SchedCallbacks(self.localManager, self["scheduler"].split('/')[-1], self._data)
        #
        # self.getManager().getProxy(self["scheduler"]).actionBegin += self.sched_callbacks.SchedActionBeginClbk
        # self.getManager().getProxy(self["scheduler"]).stateChanged += self.sched_callbacks.SchedStateChangedClbk
        self.filters = self._getCam().getFilters()
        # self.camera_callbacks = CameraCallbacks(self.getManager(), self._sex_params, self.filters)
        self._getCam().readoutComplete += self.getProxy()._CameraReadoutCompleteClbk
        self.stats = {f: {} for f in self.filters}

    def control(self):

        session = Session()
        for filter_id in self.filters:
            stats = session.query(ImageStatistics).filter(ImageStatistics.filter == filter_id,
                                                          ImageStatistics.date_obs > (
                                                          datetime.datetime.utcnow() - datetime.timedelta(
                                                              minutes=30)))

            if stats.count() > 0:
                self.stats[filter_id]["last_update"] = datetime.datetime.utcnow()
                self.stats[filter_id]["fwhm_avg"] = np.average(np.array([e.fwhm_avg for e in stats]),
                                                               weights=np.array([e.npts for e in stats]))
                self.stats[filter_id]["background_avg"] = np.average(np.array([e.background for e in stats]),
                                                                     weights=np.array([e.npts for e in stats]))
                self.stats[filter_id]["n_images"] = stats.count()
                self.log.debug(
                    "Image statistics for past 30 minutes: filter %s, n_images = %i, fwhm_avg = %3.2f, back_avg = %3.2f" % (
                        filter_id, self.stats[filter_id]["n_images"], self.stats[filter_id]["fwhm_avg"],
                        self.stats[filter_id]["background_avg"]))

            session.commit()

        return True

    def image_statistics(self, minutes):
        session = Session()
        ret = dict()
        for filter_id in self.filters:
            stats = session.query(ImageStatistics).filter(ImageStatistics.filter == filter_id,
                                                          ImageStatistics.date_obs > (
                                                          datetime.datetime.utcnow() - datetime.timedelta(
                                                              minutes=minutes)))
            ret[filter_id] = dict(date_obs=[e.date_obs for e in stats],
                                  fwhm=[e.fwhm_avg for e in stats],
                                  background=[e.background for e in stats])
        session.commit()
        return ret

    def run_stats(self, proxy, status):
        if status == CameraStatus.OK and proxy["IMAGETYP"].upper().rstrip() == "OBJECT" and \
                        proxy["SHUTTER"].upper().rstrip() == "OPEN":

            self.log.debug('%s [status:%s]@[%s]' % (proxy.filename(), status, proxy.http()))

            image_path = proxy.filename()
            if not os.path.exists(image_path):  # If image is on a remote server, donwload it.

                #  If remote is windows, image_path will be c:\...\image.fits, so use ntpath instead of os.path.
                if ':\\' in image_path:
                    modpath = ntpath
                else:
                    modpath = os.path
                image_path = ImageUtil.makeFilename(os.path.join(getImageServer(self.getManager()).defaultNightDir(),
                                                                 modpath.basename(image_path)))
                t0 = time.time()
                self.log.debug('Downloading image from server to %s' % image_path)
                if not ImageUtil.download(proxy, image_path):
                    raise ChimeraException('Error downloading image %s from %s' % (image_path, image.http()))
                self.log.debug('Finished download. Took %3.2f seconds' % (time.time() - t0))
                img = Image.fromFile(image_path)
            else:
                img = Image.fromFile(image_path)

            tmpfile = mktemp()
            p = self._sex_params
            p.update({"CATALOG_NAME": mktemp()})
            extract = img.extract(p)
            # os.unlink(tmpfile)
            # else:
            # extract = proxy.extract(self.sex_params)

            if len(extract) > 0:  # Only go ahead if at least one object was detected
                stats = np.array(
                    [[data["CLASS_STAR"], data["FLAGS"], data["FWHM_IMAGE"], data["BACKGROUND"]] for data in
                     extract])
                mask = np.bitwise_and(stats[:, 0] > 0.8, stats[:, 1] == 0)
                fff = "CLEAR"
                if "FILTER" in proxy.keys():
                    fff = proxy["FILTER"]
                # fff = "R"
                session = Session()
                try:
                    log = ImageStatistics(
                        date_obs=datetime.datetime.strptime(proxy["DATE-OBS"], "%Y-%m-%dT%H:%M:%S.%f"),
                        filename=proxy.filename(), filter=fff, fwhm_avg=np.average(stats[:, 2][mask]),
                        fwhm_std=np.std(stats[:, 2][mask]), background=np.average(stats[:, 3][mask]), npts=mask.sum(),
                        exptime=proxy["EXPTIME"])
                    session.add(log)
                finally:
                    session.commit()
                    # self.stats.append(s)
                    # print "fwhm stats:", s  # self.stats[-1]
        else:
            self.log.debug('Image %s not good for statistics. [status:%s]@[%s]' % (proxy.filename(),
                                                                                   status,
                                                                                   proxy.http()))

    def _CameraReadoutCompleteClbk(self, proxy, status):
        p = threading.Thread(target=self.run_stats, args=(proxy, status))
        # self._threadList.append(p)
        p.start()

    def __stop__(self):
        pass
