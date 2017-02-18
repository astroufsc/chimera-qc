import os
import datetime
import json

import numpy as np
from chimera.core.callback import callback
from chimera.core.chimeraobject import ChimeraObject
from chimera.core.manager import Manager
from chimera.interfaces.camera import CameraStatus

from chimera_qc.controllers.model import Session, ImageStatistics


# class SchedCallbacks(object):
#     def __init__(self, localManager, schedname, data):
#         self._data = data
#         self.schedname = schedname
#
#         @callback(localManager)
#         def SchedActionBeginClbk(action, message):
#             self.update_sched_msg(message)
#
#         @callback(localManager)
#         def SchedStateChangedClbk(newState, oldState):
#             self.update_sched_state(newState)
#
#         self.SchedStateChangedClbk = SchedStateChangedClbk
#         self.SchedActionBeginClbk = SchedActionBeginClbk
#
#     def update_sched_state(self, state):
#         self._data.update({'state': str(state),
#                            'last_update': datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')})
#         print self._data
#
#     def update_sched_msg(self, message):
#         self._data['message'] = message
#         self._data['last_update'] = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
#         print self._data


class CameraCallbacks(object):
    def __init__(self, localManager, sex_params):
        self.sex_params = sex_params
        self.stats = []

        @callback(localManager)
        def CamerareadoutComplete(proxy, status):
            if status == CameraStatus.OK and proxy["IMAGETYP"].upper().rstrip() == "OBJECT" and \
                            proxy["SHUTTER"].upper().rstrip() == "OPEN":
                print proxy.filename(), proxy.keys(), status
                extract = proxy.extract(self.sex_params)
                stats = np.array([[data["CLASS_STAR"], data["FLAGS"], data["FWHM_IMAGE"], data["BACKGROUND"]] for data in extract])
                mask = np.bitwise_and(stats[:, 0] > 0.8, stats[:, 1] == 0)
                s = [datetime.datetime.strptime(proxy["DATE-OBS"], "%Y-%m-%dT%H:%M:%S.%f"),
                     proxy.filename(), np.average(stats[:, 2][mask]), np.std(stats[:, 2][mask]),
                     np.average(stats[:, 3][mask]), mask.sum()]
                session = Session()
                try:
                    log = ImageStatistics(date_obs=s[0], filename=s[1], fwhm_avg=s[2], fwhm_std=s[3], background=s[4],
                                          npts=s[5])
                    session.add(log)
                finally:
                    session.commit()
                self.stats.append(s)
                print "fwhm stats:", self.stats[-1]

        self.CamerareadoutCompleteClbk = CamerareadoutComplete


class QualityControl(ChimeraObject):
    __config__ = {
        "camera": "/Camera/0",
        "scheduler": "/Scheduler/0",
        "sex_params": None  # json file, PARAMETER_LIST is overriden
    }

    def _getCam(self):
        return self.getManager().getProxy(self["camera"])

    def _getSched(self):
        return self.getManager().getProxy(self["scheduler"])

    def __init__(self):
        ChimeraObject.__init__(self)
        self.stats = dict()

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

        # FIXME: This should not be hardcoded!
        self.localManager = Manager("127.0.0.1", 9001)

        # self._data = dict()
        # self.sched_callbacks = SchedCallbacks(self.localManager, self["scheduler"].split('/')[-1], self._data)
        #
        # self.getManager().getProxy(self["scheduler"]).actionBegin += self.sched_callbacks.SchedActionBeginClbk
        # self.getManager().getProxy(self["scheduler"]).stateChanged += self.sched_callbacks.SchedStateChangedClbk

        self.camera_callbacks = CameraCallbacks(self.localManager, self._sex_params)
        self.getManager().getProxy(self["camera"]).readoutComplete += self.camera_callbacks.CamerareadoutCompleteClbk

    def control(self):
        for i_stat, stat in enumerate(self.camera_callbacks.stats):
            if datetime.datetime.utcnow() - stat[0] > datetime.timedelta(minutes=30):
                self.camera_callbacks.stats.pop(i_stat)
        if len(self.camera_callbacks.stats) > 0:
            self.stats["last_update"] = datetime.datetime.utcnow()
            # Here I weight each image by its number of detections!
            self.stats["fwhm_avg"] = np.average(np.array(self.camera_callbacks.stats)[:, 2],
                                                weights=np.array(self.camera_callbacks.stats)[:, 4])
            self.stats["background_avg"] = np.average(np.array(self.camera_callbacks.stats)[:, 4],
                                                weights=np.array(self.camera_callbacks.stats)[:, 4])
            self.stats["n_images"] = len(self.camera_callbacks.stats)

            self.log.debug("Image statistics for past 30 minutes: n_images = %i, fwhm_avg = %3.2f, back_avg = %3.2f" % (
                self.stats["n_images"], self.stats["fwhm_avg"], self.stats["background_avg"]))

        return True

    def image_statistics(self):
        return self.stats

    def __stop__(self):
        pass
