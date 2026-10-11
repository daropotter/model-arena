"""Passthrough FUSE filesystem: all workspace mutations share the ops lock."""
import errno
import os
from pathlib import Path

from vendor.fuse import FUSE, FuseOSError, Operations, fuse_get_context


class ObservedFS(Operations):
    def __init__(self,evidence):
        self.e=evidence
        self.handles={}

    def rel(self,path):
        return path.lstrip('/')

    def path(self,path):
        # Only the container's workspace is exposed. Never follow a backing
        # symlink into /private, /proc, credentials or the host-mounted runner.
        rel=self.rel(path)
        p=self.e.root/rel
        try:
            resolved=p.resolve()
            if not resolved.is_relative_to(self.e.root): raise FuseOSError(errno.EACCES)
        except (RuntimeError,ValueError): raise FuseOSError(errno.EACCES)
        return p

    def change(self,op,paths,fn):
        return self.e.mutate(op,[self.rel(p) for p in paths],fn,fuse_get_context()[2])

    def getattr(self,path,fh=None):
        with self.e.lock:
            st=os.fstat(fh) if fh is not None else os.lstat(self.path(path))
            values={k:getattr(st,k) for k in ('st_atime','st_ctime','st_gid','st_mode','st_mtime','st_nlink','st_size','st_uid','st_ino')}
            values.update(st_uid=1000,st_gid=1000)
            return values

    def readdir(self,path,fh):
        with self.e.lock:return ['.','..',*os.listdir(self.path(path))]

    def access(self,path,mode):
        self.path(path)
        return 0

    def open(self,path,flags):
        with self.e.lock:
            target=self.path(path)
            fn=lambda:os.open(target,flags)
            fd=self.change('truncate',[path],fn) if flags&os.O_TRUNC else fn()
            self.handles[fd]=path
            self.e.opened(self.rel(path),fuse_get_context()[2])
            return fd

    def create(self,path,mode,fi=None):
        with self.e.lock:
            fd=self.change('create',[path],lambda:os.open(self.path(path),os.O_WRONLY|os.O_CREAT|os.O_TRUNC,mode))
            self.handles[fd]=path
            return fd

    def read(self,path,size,offset,fh):
        with self.e.lock:return os.pread(fh,size,offset)

    def write(self,path,data,offset,fh):
        return self.change('write',[self.handles.get(fh,path)],lambda:os.pwrite(fh,data,offset))

    def truncate(self,path,length,fh=None):
        return self.change('truncate',[path],lambda:os.truncate(self.path(path) if fh is None else fh,length))

    def release(self,path,fh):
        with self.e.lock:
            self.handles.pop(fh,None)
            return os.close(fh)

    def flush(self,path,fh):
        os.fsync(fh);return 0

    def fsync(self,path,datasync,fh):
        os.fsync(fh);return 0

    def mkdir(self,path,mode):
        return self.change('mkdir',[path],lambda:os.mkdir(self.path(path),mode))

    def rmdir(self,path):
        return self.change('rmdir',[path],lambda:os.rmdir(self.path(path)))

    def unlink(self,path):
        return self.change('unlink',[path],lambda:os.unlink(self.path(path)))

    def rename(self,old,new):
        with self.e.lock:
            result=self.change('rename',[old,new],lambda:os.rename(self.path(old),self.path(new)))
            for fd,path in list(self.handles.items()):
                if path==old:self.handles[fd]=new
            return result

    def chmod(self,path,mode):
        return self.change('chmod',[path],lambda:os.chmod(self.path(path),mode))

    def chown(self,path,uid,gid):
        if uid not in (-1,1000) or gid not in (-1,1000):raise FuseOSError(errno.EPERM)
        return 0

    def utimens(self,path,times=None):
        with self.e.lock:return os.utime(self.path(path),times)

    def readlink(self,path):
        with self.e.lock:return os.readlink(self.path(path))

    def symlink(self,target,source):
        # fusepy signature is destination path, stored link contents.
        if os.path.isabs(source):raise FuseOSError(errno.EACCES)
        resolved=(self.path(target).parent/source).resolve()
        if not resolved.is_relative_to(self.e.root):raise FuseOSError(errno.EACCES)
        return self.change('symlink',[target],lambda:os.symlink(source,self.path(target)))

    def link(self,target,source):
        return self.change('link',[target],lambda:os.link(self.path(source),self.path(target)))

    def statfs(self,path):
        st=os.statvfs(self.e.root)
        return {k:getattr(st,k) for k in ('f_bavail','f_bfree','f_blocks','f_bsize','f_favail','f_ffree','f_files','f_flag','f_frsize','f_namemax')}


def mount(evidence,mountpoint):
    FUSE(ObservedFS(evidence),str(mountpoint),foreground=True,allow_other=True,
         nothreads=False,default_permissions=True,attr_timeout=0,entry_timeout=0,
         negative_timeout=0,direct_io=True)
