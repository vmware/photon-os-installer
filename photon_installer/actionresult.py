#/*
# * Copyright © 2020 VMware, Inc.
# * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
# */
#
#    Author: Mahmoud Bassiouny <mbassiouny@vmware.com>

# ActionResult is returned for any action
# result is a dictionary that decribes the return value
class ActionResult(object):
    def __init__(self, success, result):
        self.success = success
        self.result = result
