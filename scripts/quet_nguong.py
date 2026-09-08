"""Voi tung nguong tat, khoang im dai nhat trong vung khach dang noi la bao nhieu?

Vung khao sat: giay 11-31 (luc khach noi ma may khong dong duoc luot).
"""
import sys
import numpy as np
import soundfile as sf

x, sr = sf.read(sys.argv[1], always_2d=True)
khach = x[:, 0]
n = int(sr * 0.02)
t0, t1 = 11.0, 31.0

print("nguong_tat | khoang im dai nhat trong vung 11-31s | dong duoc luot voi SILENCE_END=?")
for nguong in (300, 400, 500, 600, 700, 800, 900, 1000):
    im, dai_nhat = 0, 0
    for i in range(int(t0 * sr), min(int(t1 * sr), len(khach) - n), n):
        rms = float(np.sqrt(np.mean(khach[i:i + n] ** 2))) * 32768
        if rms < nguong:
            im += 20
            dai_nhat = max(dai_nhat, im)
        else:
            im = 0
    moc = [m for m in (500, 750, 1000) if dai_nhat >= m]
    print(f"{nguong:10.0f} | {dai_nhat:5.0f}ms | {('dong duoc voi ' + '/'.join(map(str, moc))) if moc else 'KHONG dong duoc voi moc nao'}")
