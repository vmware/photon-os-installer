# /*
# * Copyright © 2020 VMware, Inc.
# * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
# */

import re

PRE_INSTALL = "pre-install"
POST_INSTALL = "post-install"


def replace_string_in_file(filename, search_string, replace_string):
    with open(filename, "r") as source:
        lines = source.readlines()

    with open(filename, "w") as destination:
        for line in lines:
            destination.write(re.sub(search_string, replace_string, line))
