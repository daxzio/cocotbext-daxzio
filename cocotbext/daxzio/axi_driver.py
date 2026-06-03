import math
import logging
import itertools
from random import randint, seed
from cocotb import start_soon
from cocotb.triggers import RisingEdge
from cocotbext.axi import AxiBus, AxiLiteBus
from cocotbext.axi import AxiMaster, AxiStreamBus, AxiStreamSource, AxiStreamSink, AxiStreamMonitor, AxiStreamFrame
from cocotbext.axi import AxiSlave, AxiLiteSlave, AxiLiteRam, AxiLiteRamWrite, AxiSlaveWrite, AxiSlaveRead
from .cocotbext_logger import CocoTBExtLogger

def tobytes(val, length=4):
    array = []
    for i in range(length):
        array.append((val>>(8*i))&0xff)
    return bytearray(array)

def cycle_pause(seednum=7):
    seed(seednum)
    length = randint(0, 0xfff)
    array = []
    for i in range(length):
        x = randint(0, 5)
        if 0 == x:
            array.append(1)
        else:
            array.append(0)
    return itertools.cycle(array)

def tointeger(val):
    result = 0
    for i, j in enumerate(val):
        result += int(j) << (8*i)
    return result

class AxiSinkWrite(CocoTBExtLogger):
    def __init__(self, dut, axi_prefix="m_axi", clk_name="m_aclk", reset_name=None, seednum=None, target=None):
        CocoTBExtLogger.__init__(self, type(self).__name__)
#         self.ram = SparseMemoryRegion()
        if reset_name is None:
            self.axi_slave = AxiSlaveWrite(AxiBus.from_prefix(dut, axi_prefix).write, getattr(dut, clk_name), target=target)
        else:
            self.axi_slave = AxiSlaveWrite(AxiBus.from_prefix(dut, axi_prefix).write, getattr(dut, clk_name), getattr(dut, reset_name))
        self.enable_logging()
#         self.arid = 4
        self.awid = 4
        self.axi_slave.log.setLevel(logging.WARNING)
        if seednum is not None:
            self.base_seed = seednum
        else:
            self.base_seed = randint(0,0xffffff)
        seed(self.base_seed)
        self.log.debug(f"Seed is set to {self.base_seed}")
        #self.axi_slave.log.setLevel(logging.DEBUG)
#         self.axi_slave.read_if.log.setLevel(logging.WARNING)

    async def _write(self, address, data):
        self.write(address % self.size, data)
    
    async def end_tx(self):
        while self.axi_slave.b_channel.empty():
            await RisingEdge(self.axi_slave.clock)
        while not self.axi_slave.b_channel.empty():
            await RisingEdge(self.axi_slave.clock)
    
    async def verify_memory(self, addr, data=None):
        self.data = data
        x = await self.axi_slave.target.read(addr, 4)
        #print(x)
        self.returned_val = int.from_bytes(x[::-1])
        #print(f"0x{y:08x} 0x{data:08x}")

        if not self.returned_val == self.data and not None == self.data:
            #raise Exception(f"0x{addr:08x}: Expected 0x{self.data:08x} doesn't match returned 0x{self.returned_val:08x}")
            print(f"0x{addr:08x}: Expected 0x{self.data:08x} doesn't match returned 0x{self.returned_val:08x}")
        
#     def enable_logging(self):
#         self.axi_slave.log.setLevel(logging.DEBUG)
#     
#     def disable_logging(self):
#         self.axi_slave.log.setLevel(logging.WARNING)

    def enable_write_backpressure(self, seednum=None):
        if seednum is not None:
            self.base_seed = seednum
        self.axi_slave.aw_channel.set_pause_generator(cycle_pause(self.base_seed+1))
        self.axi_slave.w_channel.set_pause_generator(cycle_pause(self.base_seed+2))
        self.axi_slave.b_channel.set_pause_generator(cycle_pause(self.base_seed+3))
    
    def enable_backpressure(self, seednum=None):
        self.enable_write_backpressure(seednum)      

    def disable_backpressure(self):
        self.axi_slave.aw_channel.set_pause_generator(itertools.cycle([0,]))
        self.axi_slave.w_channel.set_pause_generator(itertools.cycle([0,]))
        self.axi_slave.b_channel.set_pause_generator(itertools.cycle([0,]))
        
class AxiSink(CocoTBExtLogger):
    def __init__(self, dut, axi_prefix="m_axi", clk_name="m_aclk", reset_name=None, seednum=None):
        CocoTBExtLogger.__init__(self, type(self).__name__)
        self.enable_logging()
        if reset_name is None:
            self.axi_slave = AxiSlave(AxiBus.from_prefix(dut, axi_prefix), getattr(dut, clk_name))
        else:
            self.axi_slave = AxiSlave(AxiBus.from_prefix(dut, axi_prefix), getattr(dut, clk_name), getattr(dut, reset_name))
        self.arid = 4
        self.awid = 4
        self.axi_slave.write_if.log.setLevel(logging.WARNING)
        self.axi_slave.read_if.log.setLevel(logging.WARNING)
        
class AxiSinkRead(CocoTBExtLogger):
    def __init__(self, dut, axi_prefix="m_axi", clk_name="m_aclk", reset_name=None, seednum=None, target=None):
        CocoTBExtLogger.__init__(self, type(self).__name__)
#         self.ram = SparseMemoryRegion()
        if reset_name is None:
            self.axi_slave = AxiSlaveRead(AxiBus.from_prefix(dut, axi_prefix).read, getattr(dut, clk_name), target=target)
        else:
            self.axi_slave = AxiSlaveRead(AxiBus.from_prefix(dut, axi_prefix).read, getattr(dut, clk_name), getattr(dut, reset_name))
        self.enable_logging()
        self.arid = 4
#         self.awid = 4
        self.axi_slave.log.setLevel(logging.WARNING)
        if seednum is not None:
            self.base_seed = seednum
        else:
            self.base_seed = randint(0,0xffffff)
        seed(self.base_seed)
        self.log.debug(f"Seed is set to {self.base_seed}") 
        
        #self.axi_slave.log.setLevel(logging.DEBUG)
#         self.axi_slave.read_if.log.setLevel(logging.WARNING)
    async def write_random(self, addr=0, num=16):
        self.data = []
        for i in range(num):
            self.data.append(randint(0, 0xffffffff))
#             data = randint(0, 0xffffffff) 
        for i, d in enumerate(self.data):
            await self.axi_slave.target.write(addr+(i*0x4), d.to_bytes(4, 'little'))

#     async def _write(self, address, data):
#         self.write(address % self.size, data)
#     
#     async def end_tx(self):
#         while self.axi_slave.b_channel.empty():
#             await RisingEdge(self.axi_slave.clock)
#         while not self.axi_slave.b_channel.empty():
#             await RisingEdge(self.axi_slave.clock)
#     
#     async def verify_memory(self, addr, data=None):
#         self.data = data
#         x = await self.axi_slave.target.read(addr, 4)
#         #print(x)
#         self.returned_val = int.from_bytes(x[::-1])
#         #print(f"0x{y:08x} 0x{data:08x}")
# 
#         if not self.returned_val == self.data and not None == self.data:
#             #raise Exception(f"0x{addr:08x}: Expected 0x{self.data:08x} doesn't match returned 0x{self.returned_val:08x}")
#             print(f"0x{addr:08x}: Expected 0x{self.data:08x} doesn't match returned 0x{self.returned_val:08x}")
#         
# #     def enable_logging(self):
# #         self.axi_slave.log.setLevel(logging.DEBUG)
# #     
# #     def disable_logging(self):
# #         self.axi_slave.log.setLevel(logging.WARNING)

    def enable_write_backpressure(self, seednum=None):
        if seednum is not None:
            self.base_seed = seednum
        self.axi_slave.aw_channel.set_pause_generator(cycle_pause(self.base_seed+1))
        self.axi_slave.w_channel.set_pause_generator(cycle_pause(self.base_seed+2))
        self.axi_slave.b_channel.set_pause_generator(cycle_pause(self.base_seed+3))
    
    def enable_backpressure(self, seednum=None):
        self.enable_write_backpressure(seednum)      

    def disable_backpressure(self):
        self.axi_slave.aw_channel.set_pause_generator(itertools.cycle([0,]))
        self.axi_slave.w_channel.set_pause_generator(itertools.cycle([0,]))
        self.axi_slave.b_channel.set_pause_generator(itertools.cycle([0,]))
    


class AxiLiteSink(CocoTBExtLogger):
    def __init__(self, dut, axi_prefix="m_axi", clk_name="m_aclk", reset_name=None, seednum=None):
        CocoTBExtLogger.__init__(self, type(self).__name__)
        self.enable_logging()
        if reset_name is None:
            self.axi_slave = AxiLiteSlave(AxiLiteBus.from_prefix(dut, axi_prefix), getattr(dut, clk_name))
        else:
            self.axi_slave = AxiLiteSlave(AxiLiteBus.from_prefix(dut, axi_prefix), getattr(dut, clk_name), getattr(dut, reset_name))
        self.arid = 4
        self.awid = 4
        self.axi_slave.write_if.log.setLevel(logging.WARNING)
        self.axi_slave.read_if.log.setLevel(logging.WARNING)

#         if seednum is not None:
#             self.base_seed = seednum
#         else:
#             self.base_seed = randint(0,0xffffff)
#         seed(self.base_seed)
#         self.log.debug(f"Seed is set to {self.base_seed}")

    
class AxiDriver:
    def __init__(self, dut, axi_prefix="s_axi", clk_name="s_aclk", reset_name=None, seednum=None) -> None:
        self.log = logging.getLogger(f"cocotb.AxiDriver")
        self.enable_logging()
        if reset_name is None:
            self.axi_master = AxiMaster(AxiBus.from_prefix(dut, axi_prefix), getattr(dut, clk_name))
        else:
            self.axi_master = AxiMaster(AxiBus.from_prefix(dut, axi_prefix), getattr(dut, clk_name), getattr(dut, reset_name))
        self.arid = 4
        self.awid = 4
        self.axi_master.write_if.log.setLevel(logging.WARNING)
        self.axi_master.read_if.log.setLevel(logging.WARNING)
        if seednum is not None:
            self.base_seed = seednum
        else:
            self.base_seed = randint(0,0xffffff)
        seed(self.base_seed)
        self.log.debug(f"Seed is set to {self.base_seed}")
        
#         self.read_op = None
#         self._process_write_cr = None
#         if self._process_write_cr is None:
#             self._process_write_cr = start_soon(self._process_read())
        
    
    @property
    def length(self) -> int:
        if self.len is None:
            if not 0 == self.data and not self.data is None:
                return max(math.ceil(math.log2(self.data)/32)*4, 4)
            else:
                return 4
        return self.len

    @property
    def returned_val(self) -> int:
        if hasattr(self.read_op, "data"):
            if hasattr(self.read_op.data, "data"):
                return int.from_bytes(self.read_op.data.data, byteorder='little')
            else:
                return int.from_bytes(self.read_op.data, byteorder='little')
        else:
            return int.from_bytes(self.read_op, byteorder='little')
            
    def enable_logging(self) -> None:
        self.log.setLevel(logging.DEBUG)
    
    def disable_logging(self) -> None:
        self.log.setLevel(logging.WARNING)

    def enable_write_backpressure(self, seednum=None) -> None:
        if seednum is not None:
            self.base_seed = seednum
        self.axi_master.write_if.aw_channel.set_pause_generator(cycle_pause(self.base_seed+1))
        self.axi_master.write_if.w_channel.set_pause_generator(cycle_pause(self.base_seed+2))
        self.axi_master.write_if.b_channel.set_pause_generator(cycle_pause(self.base_seed+3))
    
    def enable_read_backpressure(self, seednum=None) -> None:
        if seednum is not None:
            self.base_seed = seednum
        self.axi_master.read_if.r_channel.set_pause_generator(cycle_pause(self.base_seed+4))        
        self.axi_master.read_if.ar_channel.set_pause_generator(cycle_pause(self.base_seed+5))        
    
    def enable_backpressure(self, seednum=None) -> None:
        self.enable_write_backpressure(seednum)      
        self.enable_read_backpressure(seednum)      
    
    def disable_backpressure(self) -> None:
#         self.axi_master.write_if.aw_channel.clear_pause_generator()
#         self.axi_master.write_if.w_channel.clear_pause_generator()
#         self.axi_master.write_if.b_channel.clear_pause_generator()
#     
#         self.axi_master.read_if.r_channel.clear_pause_generator()    
#         self.axi_master.read_if.ar_channel.clear_pause_generator()       
        self.axi_master.write_if.aw_channel.set_pause_generator(itertools.cycle([0,]))
        self.axi_master.write_if.w_channel.set_pause_generator(itertools.cycle([0,]))
        self.axi_master.write_if.b_channel.set_pause_generator(itertools.cycle([0,]))
    
        self.axi_master.read_if.r_channel.set_pause_generator(itertools.cycle([0,]))   
        self.axi_master.read_if.ar_channel.set_pause_generator(itertools.cycle([0,]))      
    
    
    async def poll(self, addr, data, length=None, debug=False) -> None:
        self.log.debug(f"Poll  0x{addr:08x}: for 0x{data:04x}")
        while True:
            await self.read(addr, debug=debug)
            if data == self.returned_val:
                self.log.debug(f"Condition Satisified")
                break
        return

    def check_read(self, debug=True) -> None:
        if debug:
            self.log.debug(f"Read  0x{self.addr:08x}: 0x{self.returned_val:0{self.length*2}x}")
        if not self.returned_val == self.data and not None == self.data:
            raise Exception(f"Expected 0x{self.data:08x} doesn't match returned 0x{self.returned_val:08x}")
    
    async def read(self, addr, data=None, length=None, debug=True) -> int:
        self.addr = addr
        self.data = data
        self.len = length
        self.read_op = await self.axi_master.read(self.addr, self.length, arid=self.arid)
        self.check_read(debug)
#         return self.read_op
        return self.returned_val
        

    async def write(self, addr, data=None, length=None, debug=True) -> None:
        self.len = length
        self.addr = addr
        if data is None:
            self.data = 0
            for i in range(0, self.length, 4):
                self.data = self.data | (randint(0, 0xffffffff) << i*8)
        else:
            self.data = data
        self.writedata = self.data
        if debug:
            self.log.debug(f"Write 0x{self.addr:08x}: 0x{self.data:0{self.length*2}x}")
        bytesdata = tobytes(self.data, self.length)
        #bytesdata = self.data.to_bytes(self.length, 'little')
        await self.axi_master.write(addr, bytesdata, awid=self.arid)

    async def rmodw(self, addr, data, length=None, debug=True) -> None:
        await self.read(addr, length=None, debug=False)
        newdata = data | self.returned_val
        if debug:
            self.log.debug(f"RmodW 0x{addr:08x}: 0x{self.returned_val:0{self.length*2}x} | 0x{data:0{self.length*2}x} -> 0x{newdata:0{self.length*2}x}")
        await self.write(addr, newdata, length=None, debug=False)

    
    async def _process_read(self):
        print(dir(self.axi_master.read_if))
        print(dir(self.axi_master))
        print(dir(self))
        print(self.axi_master.read_if.read_command_queue)
        print(self.axi_master.read_if.current_read_command)
        #print(self.read_op)
        await RisingEdge(self.clk)
        i = 0
        while True:
            await self.axi_master.read_if.wait()
            #if self.read_op is not None:
            print(i, True)
            i += 1

    def init_read(self, *args, **kwargs):
        self.read_op = self.axi_master.init_read(*args, **kwargs) 
    
    def read_nowait(self, addr, data=None, length=None, debug=True):
        self.addr = addr
        self.data = data
        self.len = length
        self.init_read(self.addr, self.length, arid=self.arid)
        if debug:
            self.log.debug(f"Read  0x{addr:08x}:")
    
    def write_nowait(self, addr, data=None, length=None, debug=True):
        self.len = length
        self.addr = addr
        if data is None:
            self.data = 0
            for i in range(0, self.length, 4):
                self.data = self.data | (randint(0, 0xffffffff) << i*8)
        else:
            self.data = data
        self.writedata = self.data
        if debug:
            self.log.debug(f"Write 0x{self.addr:08x}: 0x{self.data:08x}")
        bytesdata = tobytes(self.data, self.length)
        #bytesdata = self.data.to_bytes(self.length, 'little')
        self.write_op = self.axi_master.init_write(self.addr, bytesdata, awid=self.arid)

    
class AxiStreamDriver:
    def __init__(self, dut, axi_prefix="m_axi", clk_name="m_aclk", reset_name=None, seednum=None):
        self.log = logging.getLogger(f"cocotb.AxiStreamDriver")
        self.enable_logging()
        
        if reset_name is None:
            self.axis_source = AxiStreamSource(AxiStreamBus.from_prefix(dut, axi_prefix), getattr(dut, clk_name))
        else:
            self.axis_source = AxiStreamSource(AxiStreamBus.from_prefix(dut, axi_prefix), getattr(dut, clk_name), dut.reset)
        self.axis_source.log.setLevel(logging.WARNING)
        self.tdata_length = len(self.axis_source.bus.tdata)
        #self.enable_backpressure()
        
        
    def enable_logging(self):
        self.log.setLevel(logging.DEBUG)
    
    def disable_logging(self):
        self.log.setLevel(logging.WARNING)

    def enable_backpressure(self):
        base_seed = randint(0,0xffffff)
        self.axis_source.set_pause_generator(cycle_pause(base_seed))

    def disable_backpressure(self):
        #self.axis_source.clear_pause_generator()
        self.axis_source.set_pause_generator(itertools.cycle([0,]))
    
    async def write(self, tdata, length=None, **kwargs):
        if length is None:
            if 0 == tdata:
                length = int(self.tdata_length/8)
            else:
                length = math.ceil(math.log2(tdata)/self.tdata_length)*int(self.tdata_length/8)
        self.log.debug(f"Write 0x{tdata:08x}")
        #bytesdata = tdata.to_bytes(length, 'little')
        bytesdata = tobytes(tdata, length)
        frame = AxiStreamFrame(bytesdata, **kwargs)
        await self.axis_source.write(frame)

    async def wait(self):
        await self.axis_source.wait()

class AxiStreamReceiver:
    def __init__(self, dut, axi_prefix="s_axi", clk_name="s_aclk", reset_name=None, seednum=None):
        self.log = logging.getLogger(f"cocotb.AxiStreamSink")
        self.enable_logging()
        
        self.axis_sink = AxiStreamSink(AxiStreamBus.from_prefix(dut, axi_prefix), getattr(dut, clk_name))
        self.axis_sink.log.setLevel(logging.WARNING)
        self.axis_mon = AxiStreamMonitor(AxiStreamBus.from_prefix(dut, axi_prefix), getattr(dut, clk_name))
        if seednum is not None:
            self.base_seed = seednum
        else:
            self.base_seed = randint(0,0xffffff)
        seed(self.base_seed)
        self.log.debug(f"Seed is set to {self.base_seed}")
 
    @property
    def length(self):
        if self.len is None:
            if not 0 == self.data and not self.data is None:
                return math.ceil(math.log2(self.data)/32)*4
            else:
                return 4
        return self.len

    @property
    def returned_val(self):
        if hasattr(self.read_op, "data"):
            return tointeger(self.read_op.data)
        else:
            return tointeger(self.read_op)

    def check_read(self, debug=True):
        if debug:
            self.log.debug(f"Receive:          0x{self.returned_val:0{self.length*2}x}")
        if not self.returned_val == self.data and not None == self.data:
            raise Exception(f"Expected 0x{self.data:08x} doesn't match returned 0x{self.returned_val:08x}")
            
    def enable_logging(self):
        self.log.setLevel(logging.DEBUG)
    
    def disable_logging(self):
        self.log.setLevel(logging.WARNING)

    def pause(self):
        self.axis_sink.pause = True

    def unpause(self):
        self.axis_sink.pause = False

    def enable_backpressure(self, seednum=None):
        if seednum is not None:
            self.base_seed = seednum
        self.axis_sink.set_pause_generator(cycle_pause(self.base_seed))        

    async def recv(self, data=None, debug=False):
        self.data = data
        self.len = None
        self.read_op = await self.axis_sink.recv()
        self.check_read(debug)
        return self.read_op

