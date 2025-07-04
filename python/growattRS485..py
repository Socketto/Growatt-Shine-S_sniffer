import serial.tools.list_ports
import serial
import time

def GetSerial():
    for p in serial.tools.list_ports.comports():
        if p.vid == 1027 and p.pid == 24577:
            print(f"RS485 device: {p.device}")
            return p.device

TableModbusHR = dict()
TableModbusIR = dict()


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for pos in data:
        crc ^= pos
        for _ in range(8):
            if crc & 1:
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1
    return crc


class BrutalModbusParser:
    def __init__(self, modbus_id):
        self.modbus_id = modbus_id
        self.buffer = bytearray()
        self.last_request_info = None  # (start_addr, quantity)

    def feed(self, data: bytes):
        self.buffer.extend(data)
        max_search_len = 256

        i = 0
        while i < len(self.buffer) - 1:
            if self.buffer[i] == self.modbus_id and (self.buffer[i + 1] == 0x03 or self.buffer[i + 1] == 0x04):
                self.request_type =  self.buffer[i + 1]
                max_msg_len = min(max_search_len, len(self.buffer) - i)
                found_valid = False
                for msg_len in range(5, max_msg_len + 1):
                    msg = self.buffer[i : i + msg_len]
                    if len(msg) < 5:
                        continue
                    crc_calc = crc16(msg[:-2])
                    crc_msg = msg[-2] + (msg[-1] << 8)
                    if crc_calc == crc_msg:
                        # Messaggio valido
                        if msg_len == 8:
                            self._process_request(msg)
                        else:
                            self._process_response(msg)
                        del self.buffer[: i + msg_len]
                        i = -1  # riparte da zero al prossimo ciclo
                        found_valid = True
                        break
                if not found_valid:
                    i += 1
            else:
                i += 1

        if len(self.buffer) > 1024:
            self.buffer = self.buffer[-512:]

    def _process_request(self, msg: bytes):
        # Richiesta: ID + CMD + StartAddr (2) + Quantity (2) + CRC (2)
        start_addr = (msg[2] << 8) + msg[3]
        quantity = (msg[4] << 8) + msg[5]
        self.last_request_info = (start_addr, quantity)
        print(
            f"\n[RICHIESTA] Lettura da registro {start_addr} per {quantity} registri."
        )

    def _process_response(self, msg: bytes):
        global TableModbus
        # Risposta: ID + CMD + ByteCount + Dati(n) + CRC
        if len(msg) < 5:
            return
        byte_count = msg[2]
        data = msg[3 : 3 + byte_count]
        if len(data) != byte_count:
            print("[!] Byte count non corrispondente ai dati.")
            return

        registers = []
        for i in range(0, byte_count, 2):
            reg = (data[i] << 8) + data[i + 1]
            registers.append(reg)

        if self.last_request_info:
            start_addr, _ = self.last_request_info
        else:
            start_addr = 0  # se mancante, usa offset base

        print(f"\n[RISPOSTA] Registri letti da {start_addr}:")
        for idx, val in enumerate(registers):
            print(f"  Registro type:{self.request_type} -> {start_addr + idx}: {val}")
            if self.request_type == 0x03:
                TableModbusHR[start_addr + idx] = val
            if self.request_type == 0x04:
                TableModbusIR[start_addr + idx] = val


def main():
    ser = serial.Serial(port=GetSerial(), baudrate=9600, timeout=0.1)
    parser = BrutalModbusParser(modbus_id=0x01)

    try:
        while True:
            data = ser.read(64)
            if data:
                parser.feed(data)
            else:
                time.sleep(0.01)
    except KeyboardInterrupt:
        ser.close()
        print("Seriale chiusa.")
        print(dict(sorted(TableModbusHR.items())))
        print(dict(sorted(TableModbusIR.items())))


if __name__ == "__main__":
    main()
