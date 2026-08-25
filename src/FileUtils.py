import os
import shlex
import glob


def readFile(path):
    data = ""
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = f.read()
    except Exception as e:
        print(f"path: {path}, exception: {e}")
    return data


def writeFile(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(data)
    except Exception as e:
        print(f"path: {path}, exception: {e}")


def deleteFile(path):
    os.popen(f"rm {shlex.quote(path)}").read()


def deleteFiles(path, clear=False):
    for afile in glob.glob(path):
        if clear:
            writeFile(afile, "")
        deleteFile(afile)


def touchFile(path):
    os.popen(f"touch {shlex.quote(path)}").read()


def copyFile(src_path, dest_path):
    os.popen(f"cp {shlex.quote(src_path)} {shlex.quote(dest_path)}").read()


def copyFiles(src_path, dest_path):
    for afile in glob.glob(src_path):
        print(f"copying: {afile}")
        copyFile(afile, dest_path)


def moveFile(src_path, dest_path):
    os.popen(f"mv {shlex.quote(src_path)} {shlex.quote(dest_path)}").read()


def renameFile(src_path, dest_path):
    os.popen(f"mv {shlex.quote(src_path)} {shlex.quote(dest_path)}").read()


def createDirectory(path):
    os.popen(f"mkdir -p {shlex.quote(path)}").read()


def createSymlink(src, dst):
    print(f"link: src: {src} > {dst}")
    os.symlink(src, dst)


def deleteDirectory(path):
    os.popen(f"rm -rf {shlex.quote(path)}").read()
