import logging
import copy
from random import randint     
from cocotb import start_soon
from cocotb.triggers import RisingEdge, FallingEdge
from cocotb.types import LogicArray

from cocotbext.ahb import AHBBus
from cocotbext.ahb import AHBLiteMaster
from cocotbext.ahb import AHBMonitor
from cocotbext.ahb.ahb_monitor import AHBTxn
from cocotbext.ahb.ahb_types import AHBTrans, AHBWrite, AHBSize, AHBResp, AHBBurst
# from cocotbext.ahb import AHBMaster

from typing import Optional, Sequence, Union, List, Any
import collections.abc


def _logic_int(value) -> int:
    """Convert a cocotb LogicArray to int, resolving X/Z as zero.

    AHB masters may leave HWDATA undriven during read data phases (and HRDATA
    during writes); those values are don't-care per the AHB spec.
    """
    try:
        return int(value)
    except ValueError:
        if isinstance(value, LogicArray):
            return int(value.resolve("zeros"))
        raise


class AHBMonitorDX(AHBMonitor):
    def __init__(
        self, bus: AHBBus, clock: str, reset: str, prefix: str = None, **kwargs: Any
    ) -> None:
        super().__init__(bus, clock, reset, **kwargs)
        self.prefix = prefix
        self.txn_receive = False
        self.enable_log_write = False           
        self.enable_log_read = False           
        start_soon(self._log_txn())

    def _make_txn(self, txn_dict: dict) -> AHBTxn:
        is_write = int(txn_dict["hwrite"]) == int(AHBWrite.WRITE)
        wdata = _logic_int(txn_dict["hwdata"]) if is_write else 0
        rdata = _logic_int(txn_dict["hrdata"]) if not is_write else 0
        return AHBTxn(
            int(txn_dict["haddr"]),
            AHBSize(txn_dict["hsize"]),
            AHBWrite(txn_dict["hwrite"]),
            AHBBurst(txn_dict["hburst"]),
            AHBTrans(txn_dict["htrans"]),
            AHBResp(txn_dict["response"]),
            wdata,
            rdata,
        )

    async def _monitor_recv(self):
        """AHB monitor tolerant of don't-care data on the unused AHB data bus."""
        slave_error_prev = 0
        first_txn = {}
        first_st = {"phase": "none", "write_first_cycle": True}
        second_txn = {}
        second_st = {"phase": "none", "write_first_cycle": True}

        while True:
            await FallingEdge(self.clk)

            if (second_st["phase"] == "addr") and (self.bus.hready.value == 0):
                self._check_signals(second_txn)

            if first_st["phase"] == "data":
                if self.bus.hready.value == 0:
                    slave_error_prev = copy.deepcopy(self.bus.hresp.value)

                    if (first_txn["hwrite"] == 1) and (
                        first_st["write_first_cycle"] is True
                    ):
                        first_txn["hwdata"] = copy.deepcopy(self.bus.hwdata.value)
                        first_st["write_first_cycle"] = False
                    elif (first_txn["hwrite"] == 1) and (
                        first_st["write_first_cycle"] is False
                    ):
                        if self.bus.hwdata.value != first_txn["hwdata"]:
                            raise AssertionError(
                                f"[{self.bus.name}/{self.name}] AHB PROTOCOL VIOLATION: Master.hwdata signal should not change before slave.hready == 1"
                            )

                elif self.bus.hready.value == 1:
                    if (self.bus.hresp.value != AHBResp.OKAY) and (
                        slave_error_prev == 0
                    ):
                        raise AssertionError(
                            f"[{self.bus.name}/{self.name}] AHB PROTOCOL VIOLATION: Slave is not following the 2-cyle error response \
                                    - ARM IHI 0033B.b (ID102715) - Section 5.1.3"
                        )

                    first_txn["response"] = copy.deepcopy(self.bus.hresp.value)
                    first_txn["hrdata"] = copy.deepcopy(self.bus.hrdata.value)
                    first_txn["hwdata"] = copy.deepcopy(self.bus.hwdata.value)

                    self._recv(self._make_txn(first_txn))

                    first_st["phase"] = "none"
                    first_st["write_first_cycle"] = True
                    slave_error_prev = 0
                    second_st["phase"] = "none"
                    second_st["write_first_cycle"] = True

            if (self._check_valid_txn() is True) and (first_st["phase"] == "none"):
                first_st["phase"] = "data" if self.bus.hready.value == 1 else "addr"

                first_txn["hsel"] = (
                    copy.deepcopy(self.bus.hsel.value) if self.bus.hsel_exist else 0
                )
                first_txn["haddr"] = copy.deepcopy(self.bus.haddr.value)
                first_txn["htrans"] = copy.deepcopy(self.bus.htrans.value)
                first_txn["hsize"] = copy.deepcopy(self.bus.hsize.value)
                first_txn["hwrite"] = copy.deepcopy(self.bus.hwrite.value)
                first_txn["hburst"] = AHBBurst.SINGLE
                if self.bus.hburst_exist:
                    first_txn["hburst"] = copy.deepcopy(self.bus.hburst.value)
            elif (self._check_valid_txn() is True) and (first_st["phase"] == "data"):
                second_st["phase"] = "addr"

                second_txn["hsel"] = (
                    copy.deepcopy(self.bus.hsel.value) if self.bus.hsel_exist else 0
                )
                second_txn["haddr"] = copy.deepcopy(self.bus.haddr.value)
                second_txn["htrans"] = copy.deepcopy(self.bus.htrans.value)
                second_txn["hsize"] = copy.deepcopy(self.bus.hsize.value)
                second_txn["hwrite"] = copy.deepcopy(self.bus.hwrite.value)
                second_txn["hburst"] = AHBBurst.SINGLE
                if self.bus.hburst_exist:
                    second_txn["hburst"] = copy.deepcopy(self.bus.hburst.value)

            if first_st["phase"] == "addr":
                self._check_signals(first_txn)

                if self.bus.hready.value == 0:
                    raise AssertionError(
                        f"[{self.bus.name}/{self.name}] AHB PROTOCOL VIOLATION:"
                        "A slave cannot request that the address phase is extended"
                        "and therefore all slaves must be capable of sampling the address during this time"
                        " - ARM IHI 0033B.b (ID102715) - Section 1.3"
                    )
                else:
                    first_st["phase"] = "data"

    async def _log_txn(self):
        self.log.setLevel(logging.DEBUG)
        while True:
            self.txn_receive = False
            self.txn = await self.wait_for_recv()
            self.txn_receive = True
            if self.txn.mode:
                if self.enable_log_write:
                    self.log.debug(f'Write {self.prefix} 0x{self.txn.addr:08x} 0x{self.txn.wdata:08x}')
#                     print(f'Write 0x{self.txn.addr:08x} 0x{self.txn.wdata:08x}')
            else:
                if self.enable_log_read:
                    self.log.debug(f'Read  {self.prefix} 0x{self.txn.addr:08x} 0x{self.txn.rdata:08x}')
            await RisingEdge(self.clk)

    def enable_write_logging(self):
        self.log.setLevel(logging.DEBUG)
        self.enable_log_write = True           
    
    def enable_read_logging(self):
        self.log.setLevel(logging.DEBUG)
        self.enable_log_read = True           
    

class AHBLiteMasterDX(AHBLiteMaster):
    
    def __init__(
        self,
        bus: AHBBus,
        clock: str,
        reset: str,
        **kwargs,
    ):
        self.pip = False
        super().__init__(bus, clock, reset, **kwargs)

    def check_read(self):
        if not self.returned_val == self.value and not -1 == self.value:
            raise Exception(f"Expected 0x{self.value:08x} doesn't match returned 0x{self.returned_val:08x}")

# isinstance(x, (tuple, list, str))
    def prepare_addresses(self, address: Union[int, Sequence[int]], value: Union[int, Sequence[int]], length: int = 1):
        if isinstance(address, collections.abc.Sequence):
            self.addresses = address
        else:
            self.addresses = []
            for i in range(length):
                self.addresses.append(address+(i*4))
        if isinstance(value, collections.abc.Sequence):
            self.values = value
        else:
            self.values = []
            for i in range(length):
                if -1 == value:
                    self.values.append(value)
                else:
                    self.values.append((value>>(i*32)) & 0xffffffff)
    
    def enable_backpressure(self):
        self.backpressure = True

    def disable_backpressure(self):
        self.backpressure = False

        

    async def write(
        self,
        address: Union[int, Sequence[int]],
        value: Union[int, Sequence[int]],
        length: Optional[int] = 1,
        **kwargs,
    ) -> Sequence[dict]:
        self.prepare_addresses(address, value, length)

        ret = await super().write(self.addresses, self.values, **kwargs)
        for i, x in enumerate(ret):
            self.log.debug(f"Write 0x{self.addresses[i]:08x}: 0x{self.values[i]:08x}")
        return ret

    async def read(
        self,
        address: Union[int, Sequence[int]],
        value: Optional[Union[int, Sequence[int]]] = -1,
        length: Optional[int] = 1,
        **kwargs,
    ) -> Sequence[dict]:
        self.prepare_addresses(address, value, length)
        ret = await super().read(self.addresses, **kwargs)
        for i, x in enumerate(ret):
            self.returned_val = int(x['data'],16)
            self.value = self.values[i]
            self.log.debug(f"Read  0x{self.addresses[i]:08x}: 0x{self.returned_val:08x}")
            self.check_read()
        return ret
