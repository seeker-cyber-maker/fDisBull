"""Bounded JSON-lines exchange over an already-owned private pipe pair.

Product adapters own launch policy, descriptors, the channel lock, process
lifetime, public error type and cleanup. This module neither starts a process
nor retries an uncertain request. It has no dependency on either application.
"""
from __future__ import annotations

import json
import os
import select
import time


class PipeRPC:
    """Exchange mixin for an adapter with reader/writer/lock/sequence/limit.

    Adapters provide ``rpc_error_type``, ``request_prefix`` and
    ``_close_pipes()``. They may customize the EOF message without changing
    framing, deadlines or channel invalidation.
    """

    def call(self, method, params=None, timeout_ms=15000):
        deadline = time.monotonic() + timeout_ms / 1000
        if not self.lock.acquire(timeout=max(0, deadline-time.monotonic())):
            raise self.rpc_error_type('Timed out waiting for RPC channel ownership')
        try:
            if self.reader is None or self.writer is None:
                raise self.rpc_error_type('Debugger channel is closed')
            self.sequence += 1
            request_id = f'{self.request_prefix}-{self.sequence}'
            data = json.dumps({'jsonrpc':'2.0','id':request_id,'method':method,'params':params or {}},
                              allow_nan=False,separators=(',',':')).encode() + b'\n'
            if len(data) > self.limit:
                raise self.rpc_error_type('RPC request exceeds message budget')
            sent = 0
            while sent < len(data):
                self._ready(self.writer, True, deadline)
                try:
                    written = os.write(self.writer, data[sent:sent+4096])
                except (BlockingIOError,InterruptedError):
                    continue
                if not written:
                    raise OSError('RPC write made no progress')
                sent += written
            response = bytearray()
            while b'\n' not in response:
                self._ready(self.reader, False, deadline)
                try:
                    chunk = os.read(self.reader, min(65536,self.limit+1-len(response)))
                except (BlockingIOError,InterruptedError):
                    continue
                if not chunk:
                    raise OSError(self._closed_channel_message())
                response.extend(chunk)
                if len(response) > self.limit:
                    raise OSError('RPC response exceeds message budget')
            if response.find(b'\n') != len(response)-1:
                raise OSError('Unsolicited data after RPC response')
            result = json.loads(response)
            if not isinstance(result,dict) or result.get('id') != request_id or result.get('jsonrpc') != '2.0':
                raise OSError('Invalid RPC response identity')
        except BaseException:
            self._close_pipes()
            raise
        finally:
            self.lock.release()
        if 'error' in result:
            error = result['error']
            raise self.rpc_error_type(f"{error.get('message','DOSBox error')} ({error.get('data',{}).get('reason',error.get('code'))})")
        if not isinstance(result.get('result'),dict):
            self._close_pipes()
            raise self.rpc_error_type('RPC result must be an object')
        return result['result']

    @staticmethod
    def _ready(fd, writing, deadline):
        while True:
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise TimeoutError('RPC deadline expired; channel closed without replay')
            try:
                readable,writable,_ = select.select([] if writing else [fd], [fd] if writing else [], [], remaining)
                if readable or writable:
                    return
            except InterruptedError:
                continue

    def _closed_channel_message(self):
        return 'Emulator closed the RPC channel'
