#!/bin/env python3

import getopt
import gitlab
import os
import sys
import time


def main():
    do_keep_branch = False
    parent_branch = None
    private_token = None
    project_id = None
    server = None
    submodule_path = None
    submodule_sha = None

    try:
        opts, args = getopt.getopt(
                sys.argv[1:],
                "",
                longopts=["branch=", "keep-branch", "parent-branch=", "private-token=", "project-id=", "submodule-path=", "submodule-sha="]
        )
    except getopt.GetoptError as e:
        print(e.msg)
        sys.exit(2)

    for o, a in opts:
        if o in ["--branch"]:
            branch = a
        elif o in ["--keep-branch"]:
            do_keep_branch = True
        elif o in ["--parent-branch"]:
            parent_branch = a
        elif o in ["--private-token"]:
            private_token = a
        elif o in ["--project-id"]:
            project_id = a
        elif o in ["--submodule-path"]:
            submodule_path = a
        elif o in ["--submodule-sha"]:
            submodule_sha = a
        else:
            assert False, f"unhandled option {o}"

    assert branch is not None, "no branch is set"
    assert parent_branch is not None, "no parent_branch is set"
    assert private_token is not None, "no private_token is set"
    assert submodule_path is not None, "no submodule_path is set"
    assert submodule_sha is not None, "no submodule_sha is set"

    if server is None:
        server = os.environ['CI_SERVER_URL']

    gl = gitlab.Gitlab(url=server, private_token=private_token)

    project = gl.projects.get(project_id)

    project.branches.create({'branch': branch, 'ref': parent_branch})
    print(f"branch {branch} created in {project_id}", flush=True)

    response = project.update_submodule(submodule_path, branch, submodule_sha)
    print(f"sub module {submodule_path} updated to {submodule_sha}", flush=True)

    sha = response['id']

    while True:
        pipelines = project.pipelines.list(sha=sha)
        if pipelines:
            break
        print(f"waiting for pipeline for sha={sha}", flush=True)
        time.sleep(5)

    pipeline = pipelines[0]
    print(f"pipeline url is {pipeline.web_url}", flush=True)

    print(f"pipeline status is {pipeline.status}", flush=True)
    while pipeline.status not in ["success", "failed", "canceled"]:
        time.sleep(15)
        pipeline.refresh()
        print(f"pipeline status is {pipeline.status}", flush=True)

    if not do_keep_branch:
        project.branches.delete(branch)
        print(f"branch {branch} deleted")

    if pipeline.status != "success":
        print(f"pipeline failed with status {pipeline.status}", flush=True)
        sys.exit(1)

    print(f"pipeline succeeded with status {pipeline.status}", flush=True)


if __name__ == "__main__":
    main()
