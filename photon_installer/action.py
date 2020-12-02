#/*
# * Copyright © 2020 VMware, Inc.
# * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
# */
#
#
#    Author: Mahmoud Bassiouny <mbassiouny@vmware.com>


class Action(object):

    def do_action(self, params):
        raise NameError('Abstract method, this should be implemented in the child class')

    def hide(self, params):
        raise NameError('Abstract method, this should be implemented in the child class')
