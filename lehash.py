#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# for python 3.5 or earlier

import os
import fcntl
import codecs
import socket
import ctypes
import argparse
import contextlib

_libc = ctypes.CDLL('libc.so.6', use_errno=True)


class _sockaddr_alg(ctypes.Structure):
    _fields_ = [
        ('salg_family', ctypes.c_uint16),
        ('salg_type',   ctypes.c_char * 14),
        ('salg_feat',   ctypes.c_uint32),
        ('salg_mask',   ctypes.c_uint32),
        ('salg_name',   ctypes.c_char * 64),
    ]


class HashDescriptor:
    def __init__(self, fileno, digestsize):
        self.fileno = fileno
        self.digestsize = digestsize

    def digest(self, fileno, size):
        os.sendfile(self.fileno, fileno, None, size)
        os.lseek(fileno, 0, os.SEEK_SET)

        buff = b''
        size = 0

        while size < self.digestsize:
            b = os.read(self.fileno, self.digestsize - size)
            size += len(b)
            buff += b

        return buff


class Hash:
    AF_ALG = 38
    SOL_ALG = 279
    ALG_SET_KEY = 1

    ALG_TYPE = b'hash'
    ALG_NAME = None
    ALG_BYTE = None

    def __init__(self):
        sock = socket.socket(self.AF_ALG, socket.SOCK_SEQPACKET, 0)
        algo = _sockaddr_alg(self.AF_ALG, self.ALG_TYPE, 0, 0, self.ALG_NAME)

        r = _libc.bind(sock.fileno(), ctypes.byref(algo), ctypes.sizeof(algo))
        if r < 0:
            n = ctypes.get_errno()
            sock.close()
            raise OSError(n, os.strerror(n))

        self.sock = self.prepare(sock)
        self.algo = algo

    def __del__(self):
        if getattr(self, 'sock', None):
            self.sock.close()

    @classmethod
    def prepare(cls, sock):
        return sock

    @contextlib.contextmanager
    def open(self):
        try:
            fileno = _libc.accept(self.sock.fileno(), None, None)
            if fileno < 0:
                n = ctypes.get_errno()
                raise OSError(n, os.strerror(n))
            yield HashDescriptor(fileno, self.ALG_BYTE)
        finally:
            if fileno >= 0:
                os.close(fileno)

    @classmethod
    def instance(cls, name):
        return cls.algorithm()[name]()

    @classmethod
    def algorithm(cls):
        d = {}
        for c in cls.__subclasses__():
            d.update(c.algorithm())
            d[c.ALG_NAME.decode()] = c
        return d


class HashCRC32C(Hash):
    ALG_NAME = b'crc32c'
    ALG_BYTE = 4

    @classmethod
    def prepare(cls, sock):
        r = _libc.setsockopt(sock.fileno(), cls.SOL_ALG, cls.ALG_SET_KEY,
                             b'\xff' * cls.ALG_BYTE, cls.ALG_BYTE)
        if r < 0:
            n = ctypes.get_errno()
            sock.close()
            raise OSError(n, os.strerror(n))

        return sock


class HashMD5(Hash):
    ALG_NAME = b'md5'
    ALG_BYTE = 16


class HashSHA1(Hash):
    ALG_NAME = b'sha1'
    ALG_BYTE = 20


class HashSHA224(Hash):
    ALG_NAME = b'sha224'
    ALG_BYTE = 28


class HashSHA256(Hash):
    ALG_NAME = b'sha256'
    ALG_BYTE = 32


def main():
    digs = sorted(Hash.algorithm().keys())
    argp = argparse.ArgumentParser()
    argp.add_argument('-a', '--algorithm', choices=digs, default='crc32c')
    argp.add_argument('files', nargs=argparse.REMAINDER)
    args = argp.parse_args()

    with Hash.instance(args.algorithm).open() as desc:
        for path in args.files:
            with open(path) as fp:
                fileno = fp.fileno()
                fcntl.flock(fileno, fcntl.LOCK_SH)
                digest = desc.digest(fileno, os.fstat(fileno).st_size)
                print(codecs.encode(digest, 'hex').decode(), '', path)


if __name__ == '__main__':
    main()
