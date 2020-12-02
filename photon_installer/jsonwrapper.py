#/*
# * Copyright © 2020 VMware, Inc.
# * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
# */
#
#
#    Author: Sharath George <sharathg@vmware.com>


import json
import collections

class JsonWrapper(object):

    def __init__(self, filename):
        self.filename = filename

    def read(self):
        with open(self.filename) as json_data:
            self.data = json.load(json_data)
        return self.data

    def write(self, data):
        self.data = data
        with open(self.filename, 'wb') as outfile:
            json.dump(data, outfile)
