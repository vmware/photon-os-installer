#!/usr/bin/python3
# Copyright 2023 VMware, Inc.
# SPDX-License-Identifier: Apache-2.0

import os
import subprocess
import shutil
import glob


POI_TEST_PATH = os.path.dirname(os.path.abspath(__file__))
POI_PATH = os.path.dirname(POI_TEST_PATH)

REMOTE_REPO_PATH = "https://packages.vmware.com/photon"
LOCAL_REPO_PATH = POI_TEST_PATH + "/repo"

BASE_COMMAND = f"{POI_PATH}/create-image-util --poi-path {POI_PATH} --local-repo-path"
IMAGE_FLAVOR = ["azure", "ova", "rpi", "ami"]


def create_repo_path():
    os.makedirs(LOCAL_REPO_PATH, exist_ok=True)


def remove_build_images(directory):
    extensions = ["*.vhd.tar.gz", "*.ova", "*.ovf", "*.mf", "*.raw", "*.img"]

    files = [file for ext in extensions for file in glob.glob(f"{directory}/{ext}")]
    for file in files:
        try:
            os.remove(file)
        except PermissionError as e:
            print("could not remove {file}: {e}")


def setup_cleanup():
    try:
        if (os.path.exists(LOCAL_REPO_PATH)):
            shutil.rmtree(LOCAL_REPO_PATH)
    except PermissionError as e:
        subprocess.run(["sudo", "rm", "-rf", LOCAL_REPO_PATH])

    for flavor in IMAGE_FLAVOR:
        remove_build_images(os.path.join(POI_PATH, "examples", flavor))


def image_exist(flavor, image_name):
    return os.path.exists(os.path.join(POI_PATH, "examples", flavor, image_name))


class TestBuildPh5ImageWithLocalRepo:
    def setup_method(self):
        create_repo_path()

    def teardown_method(self):
        setup_cleanup()

    def test_build_ph5_local_azure_image(self):
        exec_command = f"{BASE_COMMAND} {LOCAL_REPO_PATH}/5.0 --raw-image photon-azure.raw --config-file azure_ks.yaml --flavor azure"

        subprocess.check_call(exec_command, shell = True)
        assert(image_exist("azure", "photon-azure.vhd.tar.gz") == True)

    def test_build_ph5_local_ova_image(self):
        exec_command = f"{BASE_COMMAND} {LOCAL_REPO_PATH}/5.0 --raw-image minimal.img --config-file minimal_ks.yaml --ova-config minimal.yaml --ova-name minimal --flavor ova"

        subprocess.check_call(exec_command, shell = True)
        assert(image_exist("ova", "minimal.ova") == True)

    def test_build_ph5_local_vmdk_image(self):
        exec_command = f"{BASE_COMMAND} {LOCAL_REPO_PATH}/5.0 --raw-image minimal.img --config-file minimal_ks.yaml --ova-config minimal.yaml --ova-name minimal --flavor ova --vmdk-only"

        subprocess.check_call(exec_command, shell = True)
        assert(image_exist("ova", "minimal.vmdk") == True)

    def test_build_ph5_local_ovf_mf_image(self):
        exec_command = f"{BASE_COMMAND} {LOCAL_REPO_PATH}/5.0 --raw-image minimal.img --config-file minimal_ks.yaml --ova-config minimal.yaml --ova-name minimal --flavor ova --ovf --mf"

        subprocess.check_call(exec_command, shell = True)
        assert(image_exist("ova", "minimal.ovf") == True)
        assert(image_exist("ova", "minimal.mf") == True)

    def test_build_ph5_local_lvm_ova_image(self):
        exec_command = f"{BASE_COMMAND} {LOCAL_REPO_PATH}/5.0 --raw-image minimal.img --config-file minimal_lvm_ks.yaml --ova-config minimal.yaml --ova-name minimal --flavor ova"

        subprocess.check_call(exec_command, shell = True)
        assert(image_exist("ova", "minimal.ova") == True)

    def test_build_ph5_local_ami_image(self):
        exec_command = f"{BASE_COMMAND} {LOCAL_REPO_PATH}/5.0 --config-file ami_ks.yaml --flavor ami"

        subprocess.check_call(exec_command, shell = True)
        assert(image_exist("ami", "photon-ami.raw") == True)

    '''
    def test_build_ph5_local_rpi_image(self):
        exec_command = f"{BASE_COMMAND} {LOCAL_REPO_PATH}/5.0 --config-file rpi_ks.yaml --flavor rpi --arch aarch64"

        subprocess.check_call(exec_command, shell = True)
        assert(image_exist("rmi", "rpi.img") == True)
    '''


class TestBuildPh4ImageWithLocalRepo:
    def setup_method(self):
        create_repo_path()

    def teardown_method(self):
        setup_cleanup()

    def test_build_ph4_local_azure_image(self):
        exec_command = f"{BASE_COMMAND} {LOCAL_REPO_PATH}/4.0 --raw-image photon-azure-4.0.raw --config-file azure_40_ks.yaml --flavor azure --releasever 4.0"

        subprocess.check_call(exec_command, shell = True)
        assert(image_exist("azure", "photon-azure-4.0.vhd.tar.gz") == True)

    def test_build_ph4_local_ova_image(self):
        exec_command = f"{BASE_COMMAND} {LOCAL_REPO_PATH}/4.0 --raw-image minimal.img --config-file minimal_ks.yaml --ova-config minimal.yaml --ova-name minimal --flavor ova --releasever 4.0"

        subprocess.check_call(exec_command, shell = True)
        assert(image_exist("ova", "minimal.ova") == True)

    def test_build_ph4_local_vmdk_image(self):
        exec_command = f"{BASE_COMMAND} {LOCAL_REPO_PATH}/4.0 --raw-image minimal.img --config-file minimal_ks.yaml --ova-config minimal.yaml --ova-name minimal --flavor ova --releasever 4.0 --vmdk-only"

        subprocess.check_call(exec_command, shell = True)
        assert(image_exist("ova", "minimal.vmdk") == True)

    def test_build_ph4_local_ovf_mf_image(self):
        exec_command = f"{BASE_COMMAND} {LOCAL_REPO_PATH}/4.0 --raw-image minimal.img --config-file minimal_ks.yaml --ova-config minimal.yaml --ova-name minimal --flavor ova --releasever 4.0 --ovf --mf"

    def test_build_ph4_local_lvm_ova_image(self):
        exec_command = f"{BASE_COMMAND} {LOCAL_REPO_PATH}/4.0 --raw-image minimal.img --config-file minimal_lvm_ks.yaml --ova-config minimal.yaml --ova-name minimal --flavor ova --releasever 4.0"

        subprocess.check_call(exec_command, shell = True)
        assert(image_exist("ova", "minimal.ova") == True)

    def test_build_ph4_local_ami_image(self):
        exec_command = f"{BASE_COMMAND} {LOCAL_REPO_PATH}/4.0 --config-file ami_40_ks.yaml --flavor ami --releasever 4.0"
        subprocess.check_call(exec_command, shell = True)
        assert(image_exist("ami", "photon-ami-4.0.raw") == True)

    '''
    def test_build_ph4_local_rpi_image(self):
        exec_command = f"{BASE_COMMAND} {LOCAL_REPO_PATH}/4.0 --config-file rpi_ks.yaml --flavor rpi --arch aarch64 --releasever 4.0"

        subprocess.check_call(exec_command, shell = True)
        assert(image_exist("rmi", "rpi.img") == True)
    '''


class TestBuildPh5ImageWithRemoteRepo:
    def setup_method(self):
        create_repo_path()

    def teardown_method(self):
        setup_cleanup()

    def test_build_ph5_remote_azure_image(self):
        exec_command = f"{BASE_COMMAND} {LOCAL_REPO_PATH}/5.0 --raw-image photon-azure.raw --config-file azure_ks.yaml --flavor azure --src-repo-url={REMOTE_REPO_PATH}/5.0/photon_updates_5.0_x86_64/"

        subprocess.check_call(exec_command, shell = True)
        assert(image_exist("azure", "photon-azure.vhd.tar.gz") == True)

    def test_build_ph5_remote_ova_image(self):
        exec_command = f"{BASE_COMMAND} {LOCAL_REPO_PATH}/5.0 --raw-image minimal.img --config-file minimal_ks.yaml --ova-config minimal.yaml --ova-name minimal --flavor ova --src-repo-url={REMOTE_REPO_PATH}/5.0/photon_updates_5.0_x86_64/"

        subprocess.check_call(exec_command, shell = True)
        assert(image_exist("ova", "minimal.ova") == True)

    def test_build_ph5_remote_vmdk_image(self):
        exec_command = f"{BASE_COMMAND} {LOCAL_REPO_PATH}/5.0 --raw-image minimal.img --config-file minimal_ks.yaml --ova-config minimal.yaml --ova-name minimal --flavor ova --src-repo-url={REMOTE_REPO_PATH}/5.0/photon_updates_5.0_x86_64/ --vmdk-only"

        subprocess.check_call(exec_command, shell = True)
        assert(image_exist("ova", "minimal.vmdk") == True)

    def test_build_ph5_remote_ovf_mf_image(self):
        exec_command = f"{BASE_COMMAND} {LOCAL_REPO_PATH}/5.0 --raw-image minimal.img --config-file minimal_ks.yaml --ova-config minimal.yaml --ova-name minimal --flavor ova --src-repo-url={REMOTE_REPO_PATH}/5.0/photon_updates_5.0_x86_64/ --ovf --mf"

        subprocess.check_call(exec_command, shell = True)
        assert(image_exist("ova", "minimal.ovf") == True)
        assert(image_exist("ova", "minimal.mf") == True)

    def test_build_ph5_remote_lvm_ova_image(self):
        exec_command = f"{BASE_COMMAND} {LOCAL_REPO_PATH}/5.0 --raw-image minimal.img --config-file minimal_lvm_ks.yaml --ova-config minimal.yaml --ova-name minimal --flavor ova --src-repo-url={REMOTE_REPO_PATH}/5.0/photon_updates_5.0_x86_64/"

        subprocess.check_call(exec_command, shell = True)
        assert(image_exist("ova", "minimal.ova") == True)

    def test_build_ph5_remote_ami_image(self):
        exec_command = f"{BASE_COMMAND} {LOCAL_REPO_PATH}/5.0 --config-file ami_ks.yaml --flavor ami --src-repo-url={REMOTE_REPO_PATH}/5.0/photon_updates_5.0_x86_64/"

        subprocess.check_call(exec_command, shell = True)
        assert(image_exist("ami", "photon-ami.raw") == True)

    '''
    def test_build_ph5_remote_rpi_image(self):
        exec_command = f"{BASE_COMMAND} {LOCAL_REPO_PATH}/5.0 --config-file rpi_ks.yaml --flavor rpi --arch aarch64 --src-repo-url={REMOTE_REPO_PATH}/5.0/photon_updates_5.0_x86_64/"

        subprocess.check_call(exec_command, shell = True)
        assert(image_exist("rmi", "rpi.img") == True)
    '''


class TestBuildPh4ImageWithRemoteRepo:
    def setup_method(self):
        create_repo_path()

    def teardown_method(self):
        setup_cleanup()

    def test_build_ph4_remote_azure_image(self):
        exec_command = f"{BASE_COMMAND} {LOCAL_REPO_PATH}/4.0 --raw-image photon-azure-4.0.raw --config-file azure_40_ks.yaml --flavor azure --releasever 4.0 --src-repo-url={REMOTE_REPO_PATH}/4.0/photon_updates_4.0_x86_64/"

        subprocess.check_call(exec_command, shell = True)
        assert(image_exist("azure", "photon-azure-4.0.vhd.tar.gz") == True)

    def test_build_ph4_remote_ova_image(self):
        exec_command = f"{BASE_COMMAND} {LOCAL_REPO_PATH}/4.0 --raw-image minimal.img --config-file minimal_ks.yaml --ova-config minimal.yaml --ova-name minimal --flavor ova --releasever 4.0 --src-repo-url={REMOTE_REPO_PATH}/4.0/photon_updates_4.0_x86_64/"

        subprocess.check_call(exec_command, shell = True)
        assert(image_exist("ova", "minimal.ova") == True)

    def test_build_ph4_remote_vmdk_image(self):
        exec_command = f"{BASE_COMMAND} {LOCAL_REPO_PATH}/4.0 --raw-image minimal.img --config-file minimal_ks.yaml --ova-config minimal.yaml --ova-name minimal --flavor ova --releasever 4.0 --src-repo-url={REMOTE_REPO_PATH}/4.0/photon_updates_4.0_x86_64/ --vmdk-only"

        subprocess.check_call(exec_command, shell = True)
        assert(image_exist("ova", "minimal.vmdk") == True)

    def test_build_ph4_remote_ovf_mf_image(self):
        exec_command = f"{BASE_COMMAND} {LOCAL_REPO_PATH}/4.0 --raw-image minimal.img --config-file minimal_ks.yaml --ova-config minimal.yaml --ova-name minimal --flavor ova --releasever 4.0 --src-repo-url={REMOTE_REPO_PATH}/4.0/photon_updates_4.0_x86_64/ --ovf --mf"

        subprocess.check_call(exec_command, shell = True)
        assert(image_exist("ova", "minimal.ovf") == True)
        assert(image_exist("ova", "minimal.mf") == True)

    def test_build_ph4_remote_lvm_ova_image(self):
        exec_command = f"{BASE_COMMAND} {LOCAL_REPO_PATH}/4.0 --raw-image minimal.img --config-file minimal_lvm_ks.yaml --ova-config minimal.yaml --ova-name minimal --flavor ova --releasever 4.0 --src-repo-url={REMOTE_REPO_PATH}/4.0/photon_updates_4.0_x86_64/"

        subprocess.check_call(exec_command, shell = True)
        assert(image_exist("ova", "minimal.ova") == True)

    def test_build_ph4_remote_ami_image(self):
        exec_command = f"{BASE_COMMAND} {LOCAL_REPO_PATH}/4.0 --config-file ami_40_ks.yaml --flavor ami --releasever 4.0 --src-repo-url={REMOTE_REPO_PATH}/4.0/photon_updates_4.0_x86_64/"

        subprocess.check_call(exec_command, shell = True)
        assert(image_exist("ami", "photon-ami-4.0.raw") == True)

    '''
    def test_build_ph4_remote_rpi_image(self):
        exec_command = f"{BASE_COMMAND} {LOCAL_REPO_PATH}/4.0 --config-file rpi_ks.yaml --flavor rpi --arch aarch64 --releasever 4.0 --src-repo-url={REMOTE_REPO_PATH}/4.0/photon_updates_4.0_x86_64/"

        subprocess.check_call(exec_command, shell = True)
        assert(image_exist("rmi", "rpi.img") == True)
    '''
