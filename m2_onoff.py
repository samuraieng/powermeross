import asyncio
import ipaddress
import os
import re
import socket
import subprocess

from datetime import datetime
from meross_iot.http_api import MerossHttpClient
from meross_iot.manager import MerossManager

EMAIL = os.environ["MEROSS_UID"]
PASSWORD = os.environ["MEROSS_PID"]
TARGET_UUID = os.environ["MEROSS_TID"]
HOME_NET = ipaddress.ip_network("192.168.1.0/24")

def in_home_network() -> bool:
    # デフォルトルート向けの自分のIPを取得(パケットは送らない)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        my_ip = ipaddress.ip_address(s.getsockname()[0])
    finally:
        s.close()
    return my_ip in HOME_NET

def battery_percent() -> int:
    out = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True).stdout
    m = re.search(r"(\d+)%", out)
    return int(m.group(1))

async def set_power(turn_on: bool):
    client = await MerossHttpClient.async_from_user_password(
        email=EMAIL, password=PASSWORD, api_base_url="https://iotx-ap.meross.com"
    )
    manager = MerossManager(http_client=client)
    await manager.async_init()
    await manager.async_device_discovery()
    devices = manager.find_devices(device_uuids=[TARGET_UUID])

    if devices:
        dev = devices[0]
        await dev.async_update()
        if turn_on and not dev.is_on():
            await dev.async_turn_on(channel=0)
            print(f"{dev.name}: OFF -> ON")
        elif not turn_on and dev.is_on():
            await dev.async_turn_off(channel=0)
            print(f"{dev.name}: ON -> OFF")
        else:
            print(f"{dev.name}: 変更なし (is_on={dev.is_on()})")
    else:
        print("デバイスが見つかりません")

    manager.close()
    await client.async_logout()

def thresholds(hour: int):
    # 2:00 ON / 5:00 OFF を行う別プログラムの充電を打ち消さないよう、深夜帯は100%までOFFにしない
    if 2 <= hour < 5:
        return 20, 100
    return 20, 70

def main():
    on_below, off_at = thresholds(datetime.now().hour)

    if not in_home_network():
        print("自宅ネットワーク外なのでスキップ")
        return

    pct = battery_percent()
    print(f"バッテリー残量: {pct}%")

    if pct <= on_below:
        asyncio.run(set_power(True))
    elif pct >= off_at:
        asyncio.run(set_power(False))
    else:
        print(f"{on_below}% < 残量 < {off_at}% のため何もしない")

main()
