#!/usr/bin/python2.6

# This file is a part of Metagam project.
#
# Metagam is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# any later version.
# 
# Metagam is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with Metagam.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import print_function
from mg import *
from concurrence import Tasklet
import subprocess
import sys
import re
import json

re_class = re.compile('^upstream (\S+) {')

class Server(Module):
    def register(self):
        self.rdep(["mg.core.cluster.Cluster", "mg.core.web.Web"])
        self.rhook("int-server.spawn", self.spawn, priv="public")
        self.rhook("int-server.nginx", self.nginx, priv="public")
        self.rhook("core.fastidle", self.fastidle)
        self.executable = re.sub(r'[^\/]+$', 'mg_worker', sys.argv[0])

    def running_workers(self):
        """
        returns map of currently running worker processes (worker_id => process)
        """
        app = self.app()
        try:
            return app.running_workers
        except AttributeError:
            app.running_workers = {"count": 0}
            return app.running_workers

    def spawn(self):
        request = self.req()
        workers = self.running_workers()
        new_count = int(request.param("workers"))
        old_count = workers["count"]
        instid = self.app().instid
        if new_count < old_count: 
            # Killing
            workers["count"] = new_count
            for i in range(new_count, old_count):
                process = workers[i]
                self.debug("terminating child %d (pid %d)", i, process.pid)
                process.terminate()
                del workers[i]
        elif new_count > old_count:
            # Spawning
            for i in range(old_count, new_count):
                self.debug("running child %d (process %s)", i, self.executable)
                try:
                    workers[i] = subprocess.Popen([self.executable, str(instid), str(i)], close_fds=True)
                except OSError, e:
                    raise RuntimeError("Running %s: %s" % (self.executable, e))
            workers["count"] = new_count
        self.call("web.response_json", {"ok": 1})

    def fastidle(self):
        workers = self.running_workers()
        instid = self.app().instid
        for i in range(0, workers["count"]):
            workers[i].poll()
            if workers[i].returncode is not None:
                self.debug("respawning child %d (process %s)", i, self.executable)
                workers[i] = subprocess.Popen([self.executable, str(instid), str(i)], close_fds=True)
        self.call("core.check_last_ping")

    def nginx(self):
        req = self.req()
        workers = json.loads(req.param("workers"))
        filename = "/etc/nginx/nginx-metagam.conf"
        classes = set()
        try:
            with open(filename, "r") as f:
                for line in f:
                    m = re_class.match(line)
                    if m:
                        cls = m.group(1)
                        classes.add(cls)
        except IOError as e:
            pass
        try:
            with open(filename, "w") as f:
                for cls, list in workers.iteritems():
                    try:
                        classes.remove(cls)
                    except KeyError:
                        pass
                    print("upstream %s {" % cls, file=f)
                    for srv in list:
                        print("\tserver %s:%d;" % (srv[0], srv[1]), file=f)
                    print("}", file=f)
                for cls in classes:
                    print("upstream %s {" % cls, file=f)
                    print("\tserver 127.0.0.1:65534;", file=f)
                    print("}", file=f)
            subprocess.check_call(["/usr/bin/sudo", "/etc/init.d/nginx", "reload"])
        except IOError as e:
            self.error("Error writing %s: %s", filename, e)
            self.call("web.internal_server_error")
        except subprocess.CalledProcessError as e:
            self.error("Error reloading nginx: %s", e)
            self.call("web.internal_server_error")
        self.call("web.response_json", {"ok": 1})
