"""Guarded backing selection and mutation-boundary invalidation.

This is a mapping control plane, not a cartridge mapper or interrupt scheduler.
Compiled/recovered artifacts may be reused; authority to execute is epoch-bound.
"""
from __future__ import annotations
from dataclasses import dataclass
from threading import RLock
from uuid import uuid4
from hashlib import sha256
from typing import Callable, TypeVar
from .model import Admission, Bindings, NativeBacking, RecoveredBlock, Refused, StaleSelection
from .recover import recover

T=TypeVar('T')


@dataclass(frozen=True)
class Lease:
    owner: str
    slot: str
    epoch: int
    dependencies: tuple[tuple[str,int,str],...]
    block_identity: str
    serial: int


@dataclass(frozen=True)
class Checkpoint:
    owner: str
    bindings: tuple[tuple[str,NativeBacking],...]
    serial: int


class CodeMap:
    """One stateful authority per source execution context."""
    def __init__(self):
        self._owner=uuid4().hex
        self._slots:dict[str,tuple[int,NativeBacking]]={}
        self._epoch=0
        self._generation=0
        self._serial=0
        self._snapshot_serial=0
        self._snapshots:dict[int,Checkpoint]={}
        self._issued:dict[int,tuple[Lease,RecoveredBlock]]={}
        self._cache:dict[tuple[str,str,Admission],RecoveredBlock]={}
        self._lock=RLock()
        self._dispatching=False
        self.cache_hits=0
        self.recoveries=0

    def _mutation_allowed(self):
        if self._dispatching:
            raise Refused('mapping mutation during an admitted block is unsupported')

    def map(self,slot:str,backing:NativeBacking)->None:
        if not isinstance(slot,str) or not slot or not isinstance(backing,NativeBacking):
            raise Refused('a named slot and immutable backing are required')
        with self._lock:
            self._mutation_allowed()
            self._generation+=1
            self._slots[slot]=(self._generation,backing)
            # Prune only affected authority records; keep safe cached derivations.
            self._issued={k:v for k,v in self._issued.items()
                          if all(dep[0]!=slot for dep in v[0].dependencies)}

    def select(self,slot:str,bindings:Bindings,admission:Admission=Admission(),
               dependencies:tuple[str,...]=())->tuple[Lease,RecoveredBlock]:
        admission.validate()
        with self._lock:
            try:
                backing=self._slots[slot][1]
                names=sorted(set((slot,*dependencies)))
                vector=tuple((n,self._slots[n][0],self._slots[n][1].identity) for n in names)
            except KeyError as exc:
                raise Refused('unbound mapping dependency: '+str(exc)) from exc
            key=(backing.identity,bindings.identity,admission)
            if key in self._cache:
                block=self._cache[key];self.cache_hits+=1
            else:
                block=recover(backing,bindings,admission)
                self._cache[key]=block;self.recoveries+=1
            self._serial+=1
            lease=Lease(self._owner,slot,self._epoch,vector,block.identity,self._serial)
            self._issued[lease.serial]=(lease,block)
            return lease,block

    def validate(self,lease:Lease)->RecoveredBlock:
        with self._lock:
            if not isinstance(lease,Lease) or lease.owner!=self._owner or lease.epoch!=self._epoch:
                raise StaleSelection('selection belongs to a different context or restore epoch')
            issued=self._issued.get(lease.serial)
            if issued is None or issued[0]!=lease:
                raise StaleSelection('selection was invalidated or was not issued here')
            for name,generation,identity in lease.dependencies:
                current=self._slots.get(name)
                if current is None or current[0]!=generation or current[1].identity!=identity:
                    raise StaleSelection('mapping dependency changed: '+name)
            return issued[1]

    def dispatch(self,lease:Lease,run:Callable[[RecoveredBlock],T])->T:
        """Validate immediately before use; hold stable mapping through the block.

        This protects this registry only. It neither locks an emulator bus nor
        rolls back external effects from an arbitrary callback.
        """
        with self._lock:
            block=self.validate(lease)
            if self._dispatching: raise Refused('reentrant dispatch is not admitted')
            self._dispatching=True
            try:
                result=run(block)
                self.validate(lease)
                return result
            finally:
                self._dispatching=False

    def execute(self,lease:Lease,implementation,state:dict)->dict:
        """Run a realization bound to exactly this shared-IL semantic revision.

        This is an identity/selection guard, not a proof that arbitrary supplied
        implementation code honors its declaration. Built-in C realizations are
        qualified by the separate conformance tests and artifact receipts.
        """
        def run(block):
            if getattr(implementation,'semantic_sha256',None)!=sha256(block.document_bytes).hexdigest():
                raise Refused('implementation does not match the selected semantic revision')
            return implementation.run(state)
        return self.dispatch(lease,run)

    def snapshot(self)->Checkpoint:
        with self._lock:
            self._mutation_allowed()
            self._snapshot_serial+=1
            checkpoint=Checkpoint(self._owner,tuple(sorted((n,v[1]) for n,v in self._slots.items())),self._snapshot_serial)
            self._snapshots[checkpoint.serial]=checkpoint
            return checkpoint

    def restore(self,snapshot:Checkpoint)->None:
        with self._lock:
            self._mutation_allowed()
            if (not isinstance(snapshot,Checkpoint) or snapshot.owner!=self._owner
                    or self._snapshots.get(snapshot.serial)!=snapshot):
                raise Refused('checkpoint is unissued, modified or belongs to another source context')
            self._epoch+=1
            self._issued.clear()
            self._slots.clear()
            for name,backing in snapshot.bindings:
                self._generation+=1
                self._slots[name]=(self._generation,backing)

    def patch(self,slot:str,expected_identity:str,offset:int,replacement:bytes)->NativeBacking:
        with self._lock:
            self._mutation_allowed()
            if slot not in self._slots: raise Refused('unbound slot')
            old=self._slots[slot][1]
            if old.identity!=expected_identity: raise StaleSelection('patch expected a different source revision')
            if type(offset)is not int or not isinstance(replacement,bytes) or not replacement:
                raise Refused('patch requires a nonempty byte replacement and integer offset')
            if offset<0 or offset+len(replacement)>len(old.code):
                raise Refused('patch must remain inside its retained backing')
            code=old.code[:offset]+replacement+old.code[offset+len(replacement):]
            new=NativeBacking(old.image_id,old.bank_id,old.entry,code,old.cpu_profile)
            self.map(slot,new)
            return new
