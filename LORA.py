import spidev
import struct
import OPi.GPIO as GPIO
from time import sleep

class RFM98:
    def __init__(self, bus=1, device=0):
        self.spi = spidev.SpiDev()
        self.spi.open(bus, device)
        self.spi.max_speed_hz = 500000  # Set the appropriate SPI speed
        self.spi.mode = 0b00
        
        self.NSS_PIN = 24
        self.DIO0_PIN = 8
        
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(self.NSS_PIN, GPIO.OUT)
        GPIO.setup(self.DIO0_PIN, GPIO.IN)
        self.config()

    @staticmethod
    def lookup_mode(mode_name):
        return MODES.get_mode(mode_name)

    @staticmethod
    def lookup_IrqFlag(IqrFlag):
        return MASK.get_flag(IqrFlag)

    @staticmethod
    def lookup_register(register_name):
        return RegMap.get_register(register_name)

    def config(self):
        self.set_register('OP_MODE', 128)
        self.set_register('OP_MODE', 129)
        self.set_register('PA_CONFIG', 220)
        self.set_register('OP_MODE', 11)
        

    def set_NSS_pin(self):
        GPIO.output(self.NSS_PIN, GPIO.LOW) 
	
    def unset_NSS_pin(self):
        GPIO.output(self.NSS_PIN, GPIO.HIGH)

    def reg_write(self, addr, data):
        self.set_NSS_pin()
        data = self.spi.xfer([addr | 0x80] + [data])[1]
        self.unset_NSS_pin()
        #print('Value Written to Register ', hex(addr) , 'is ', hex(data))

    def reg_read(self, addr):
        self.set_NSS_pin()
        data = self.spi.xfer([addr, 0x00])[1]
        self.unset_NSS_pin()
        #print('Value Read From ', hex(addr), ' is ', hex(data))
        return data

    def set_register(self, register_name, value):
        register = self.lookup_register(register_name)
        self.reg_write(register, value)

    def read_register(self, register_name):
        register = self.lookup_register(register_name)
        return self.reg_read(register)

    def get_mode(self):
        mode_value = self.read_register('OP_MODE')
        for mode, value in MODES.Modes.items():
            if value == mode_value:
                return mode
        return None

    def set_mode(self, mode_name):
        mode_value = self.lookup_mode(mode_name)
        if mode_value is not None:
            self.set_register('OP_MODE', mode_value)
        else:
            print("Invalid mode name: ", mode_name)

    def init_Tx_fifo_addr_ptr(self):
        fifo_tx_base_addr = self.read_register('FIFO_TX_BASE_ADDR')
        self.set_register('FIFO_ADDR_PTR', fifo_tx_base_addr)

    def init_Rx_fifo_addr_ptr(self):
        fifo_rx_base_addr = self.read_register('FIFO_RX_BASE_ADDR')
        self.set_register('FIFO_ADDR_PTR', fifo_rx_base_addr)

    def write_to_fifo(self, data_list):
        self.set_register('FIFO', data_list)

    def read_and_clear_irq_flags(self):
        irq_flags = self.read_register('IRQ_FLAGS')
        while irq_flags & 0x08:
            self.set_register('IRQ_FLAGS', 0x08)  # Clear IrqFlags
            irq_flags = self.read_register('IRQ_FLAGS')
        return irq_flags

    def transmit(self, data_list):
        payload_size = len(data_list)
        self.set_register('PAYLOAD_LENGTH', payload_size)
        
        self.init_Tx_fifo_addr_ptr()

        self.set_mode('STDBY')  # Standby Mode
        register = self.lookup_register('FIFO')

        self.set_NSS_pin()
        data = self.spi.xfer([register | 0x80] + data_list)[1:]
        self.unset_NSS_pin()
        print("Data being sent:", data)
        
        self.set_mode('TX')  # Transmit Mode
        mode = self.get_mode()
        print("MODE =", mode)
        sleep(0.2)

        irq_flags = self.read_and_clear_irq_flags()
        #print("IrqFlags =", irq_flags)

        self.set_mode('STDBY')  # Standby Mode

        self.set_register('IRQ_FLAGS', 0xFF)  # Clear All IrqFlags
        print('      ')

    def receive(self): 
        self.set_mode('RXCONT')  # Set the module to receive mode

        mode = self.get_mode()
        print("MODE =", mode)
        

        while True:
            modem_status = self.read_register('MODEM_STAT')  # Read the modem status
            #print("Modem Status:", modem_status)
            irq_flags = self.read_register('IRQ_FLAGS')  # Read the IRQ flags
            #print("Irq Flags =", irq_flags)
            self.init_Rx_fifo_addr_ptr();          
            if irq_flags & 0x50:  # Check if valid_header or rx_done flags are set
                valid_header = (irq_flags & 0x10) >> 4
                rx_done = (irq_flags & 0x40) >> 6
                
                #if valid_header or rx_done:
                    #print("Packet")            
                packet_length = self.read_register('RX_NB_BYTES')  # Read the packet length
                print("Num of Bytes:", packet_length)
                #recv_data = self.read_register('FIFO')
                register = self.lookup_register('FIFO')
                self.set_NSS_pin()
                recv_data = self.spi.xfer([register, 0x00] + [0]*(packet_length-1))[1:]
                self.unset_NSS_pin()
                value = struct.unpack("<fff", bytes(recv_data))
                print("Received Packet = ", value)

                self.set_register('IRQ_FLAGS', 0xFF)  # Clear the IRQ flags
                self.set_mode('STDBY')  # Set the module to standby mode

                rx_current_addr = self.read_register('FIFO_RX_CURR_ADDR')  # Read the current address in FIFO
                self.set_register('FIFO_ADDR_PTR', rx_current_addr) # Initialize FifoAddrPtr to RxCurrentAddr
                break  # Exit the loop and complete the cycle

            sleep(0.2)  # Wait for a short duration before checking for received data
            print('      ')
        
        
class MODES:
    Modes = {
        'SLEEP'     : 0x88,
        'STDBY'     : 0x89,
        'FSTX'      : 0x8A,
        'TX'        : 0x8B,
        'FSRX'      : 0x8C,
        'RXCONT'    : 0x8D,
        'RXSINGLE'  : 0x8E,
        'CAD'       : 0x8F
    }

    @staticmethod
    def get_mode(mode_name):
        return MODES.Modes.get(mode_name)
        
class MASK:
    IRQ_FLAGS = {
        'RxTimeout'           : 7,
        'RxDone'              : 6,
        'PayloadCrcError'     : 5,
        'ValidHeader'         : 4,
        'TxDone'              : 3,
        'CadDone'             : 2,
        'FhssChangeChannel'   : 1,
        'CadDetected'         : 0
    }

    @staticmethod
    def get_flag(IqrFlag):
        return MASK.IRQ_FLAGS.get(IqrFlag)
        
class RegMap:
    registers = {
        'FIFO'               : 0x00,
        'OP_MODE'            : 0x01,
        'FR_MSB'             : 0x06,
        'FR_MID'             : 0x07,
        'FR_LSB'             : 0x08,
        'PA_CONFIG'          : 0x09,
        'PA_RAMP'            : 0x0A,
        'OCP'                : 0x0B,
        'LNA'                : 0x0C,
        'FIFO_ADDR_PTR'      : 0x0D,
        'FIFO_TX_BASE_ADDR'  : 0x0E,
        'FIFO_RX_BASE_ADDR'  : 0x0F,
        'FIFO_RX_CURR_ADDR'  : 0x10,
        'IRQ_FLAGS_MASK'     : 0x11,
        'IRQ_FLAGS'          : 0x12,
        'RX_NB_BYTES'        : 0x13,
        'RX_HEADER_CNT_MSB'  : 0x14,
        'RX_PACKET_CNT_MSB'  : 0x16,
        'MODEM_STAT'         : 0x18,
        'PKT_SNR_VALUE'      : 0x19,
        'PKT_RSSI_VALUE'     : 0x1A,
        'RSSI_VALUE'         : 0x1B,
        'HOP_CHANNEL'        : 0x1C,
        'MODEM_CONFIG_1'     : 0x1D,
        'MODEM_CONFIG_2'     : 0x1E,
        'SYMB_TIMEOUT_LSB'   : 0x1F,
        'PREAMBLE_MSB'       : 0x20,
        'PAYLOAD_LENGTH'     : 0x22,
        'MAX_PAYLOAD_LENGTH' : 0x23,
        'HOP_PERIOD'         : 0x24,
        'FIFO_RX_BYTE_ADDR'  : 0x25,
        'MODEM_CONFIG_3'     : 0x26,
        'PPM_CORRECTION'     : 0x27,
        'FEI_MSB'            : 0x28,
        'DETECT_OPTIMIZE'    : 0X31,
        'INVERT_IQ'          : 0x33,
        'DETECTION_THRESH'   : 0X37,
        'SYNC_WORD'          : 0X39,
        'DIO_MAPPING_1'      : 0x40,
        'DIO_MAPPING_2'      : 0x41,
        'VERSION'            : 0x42,
        'TCXO'               : 0x4B,
        'PA_DAC'             : 0x4D,
        'AGC_REF'            : 0x61,
        'AGC_THRESH_1'       : 0x62,
        'AGC_THRESH_2'       : 0x63,
        'AGC_THRESH_3'       : 0x64,
        'PLL'                : 0x70
    }

    @staticmethod
    def get_register(register_name):
        return RegMap.registers.get(register_name)


rfm = RFM98()

while True:
    data_pack = struct.pack("<fff", 22.25, 0.176, 56.8584)
    data_list = list(data_pack)
    rfm.transmit(data_list)
    #rfm.receive()

