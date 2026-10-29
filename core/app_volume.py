# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Hariku's own volume (core 2.13): the master volume of Hariku's audio session,
the "Hariku" slider in Windows' Volume Mixer, through the Core Audio API with
plain ctypes COM (the helpers of core/voice_sapi.py).

Before 2.13 the volume was set with waveOutSetVolume, which on Windows Vista
and later sets the session's left and right channel volumes. NVDA's sound
split sets every application's channel volumes too, so each time NVDA
started, Hariku was back at full volume. NVDA leaves the master volume alone
(unless its own "volume of other applications" is turned on), and every sound
Hariku and its extensions play (MCI, winsound, a voice) goes through this one
session, so one setting still covers them all.
"""
import ctypes
import ctypes.wintypes as wt
import logging

from core import voice_sapi as com

logger = logging.getLogger(__name__)

CLSID_MMDeviceEnumerator = "{BCDE0395-E52F-467C-8E3D-C4579291692E}"
IID_IMMDeviceEnumerator = "{A95664D2-9614-4F35-A746-DE8DB63617E6}"
IID_IAudioSessionManager = "{BFA971F1-4D5E-40BB-935E-967039BFBEE4}"

E_RENDER = 0
DEVICE_STATE_ACTIVE = 0x1
S_FALSE = 1

# Vtable slots (IUnknown takes 0-2).
ENUMERATOR_ENUM_AUDIO_ENDPOINTS = 3
COLLECTION_GET_COUNT = 3
COLLECTION_ITEM = 4
DEVICE_ACTIVATE = 3
SESSION_MANAGER_GET_SIMPLE_AUDIO_VOLUME = 4
SIMPLE_VOLUME_SET_MASTER_VOLUME = 3
SIMPLE_VOLUME_GET_MASTER_VOLUME = 4


def _simple_volumes():
    """The ISimpleAudioVolume of Hariku's default audio session on every active
    output device (a sound may go to any of them). The caller releases them."""
    enumerator = com.create(CLSID_MMDeviceEnumerator, IID_IMMDeviceEnumerator,
                            what="MMDeviceEnumerator")
    collection = com.Interface(None)
    volumes = []
    try:
        ptr = ctypes.c_void_p()
        enumerator.call(ENUMERATOR_ENUM_AUDIO_ENDPOINTS,
                        (ctypes.c_int, wt.DWORD, ctypes.POINTER(ctypes.c_void_p)),
                        E_RENDER, DEVICE_STATE_ACTIVE, ctypes.byref(ptr),
                        what="IMMDeviceEnumerator::EnumAudioEndpoints")
        collection = com.Interface(ptr)
        count = wt.UINT()
        collection.call(COLLECTION_GET_COUNT, (ctypes.POINTER(wt.UINT),), ctypes.byref(count),
                        what="IMMDeviceCollection::GetCount")
        for index in range(count.value):
            device = com.Interface(None)
            manager = com.Interface(None)
            try:
                ptr = ctypes.c_void_p()
                collection.call(COLLECTION_ITEM, (wt.UINT, ctypes.POINTER(ctypes.c_void_p)),
                                index, ctypes.byref(ptr), what="IMMDeviceCollection::Item")
                device = com.Interface(ptr)
                ptr = ctypes.c_void_p()
                device.call(DEVICE_ACTIVATE,
                            (ctypes.POINTER(com.GUID), wt.DWORD, ctypes.c_void_p,
                             ctypes.POINTER(ctypes.c_void_p)),
                            ctypes.byref(com.guid(IID_IAudioSessionManager)), com.CLSCTX_ALL,
                            None, ctypes.byref(ptr), what="IMMDevice::Activate")
                manager = com.Interface(ptr)
                ptr = ctypes.c_void_p()
                manager.call(SESSION_MANAGER_GET_SIMPLE_AUDIO_VOLUME,
                             (ctypes.c_void_p, wt.DWORD, ctypes.POINTER(ctypes.c_void_p)),
                             None, 0, ctypes.byref(ptr),
                             what="IAudioSessionManager::GetSimpleAudioVolume")
                volumes.append(com.Interface(ptr))
            except OSError as e:
                logger.debug(f"App volume: output device {index} skipped: {e}")
            finally:
                manager.release()
                device.release()
    except BaseException:
        for volume in volumes:
            volume.release()
        raise
    finally:
        collection.release()
        enumerator.release()
    return volumes


def _with_com(work):
    """Run `work()` with COM initialised on this thread (wx's main thread
    already has it; a worker thread may not)."""
    hresult = com._ole32().CoInitializeEx(None, com.COINIT_APARTMENTTHREADED)
    try:
        return work()
    finally:
        if hresult in (com.S_OK, S_FALSE):
            com._ole32().CoUninitialize()


def set_volume(percent):
    """Set Hariku's session volume to `percent` (0-100) on every output device.
    Returns how many devices took it; 0 when Windows' audio can't be reached
    (the error is logged, never raised)."""
    level = ctypes.c_float(max(0, min(100, int(percent))) / 100.0)

    def work():
        volumes = _simple_volumes()
        done = 0
        try:
            for volume in volumes:
                try:
                    volume.call(SIMPLE_VOLUME_SET_MASTER_VOLUME, (ctypes.c_float, ctypes.c_void_p),
                                level, None, what="ISimpleAudioVolume::SetMasterVolume")
                    done += 1
                except OSError as e:
                    logger.debug(f"App volume: a device refused the volume: {e}")
        finally:
            for volume in volumes:
                volume.release()
        return done

    try:
        return _with_com(work)
    except Exception as e:
        logger.warning(f"App volume: could not set Hariku's volume: {e}")
        return 0


def get_volume():
    """Hariku's session volume (0-100) on the first output device, or None."""
    def work():
        volumes = _simple_volumes()
        try:
            for volume in volumes:
                level = ctypes.c_float()
                volume.call(SIMPLE_VOLUME_GET_MASTER_VOLUME, (ctypes.POINTER(ctypes.c_float),),
                            ctypes.byref(level), what="ISimpleAudioVolume::GetMasterVolume")
                return int(round(level.value * 100))
            return None
        finally:
            for volume in volumes:
                volume.release()

    try:
        return _with_com(work)
    except Exception as e:
        logger.debug(f"App volume: could not read Hariku's volume: {e}")
        return None


def reset_channel_volume():
    """Put the left and right channel volumes that waveOutSetVolume set before
    2.13 back to full, so the old setting doesn't stay under the new one."""
    try:
        ctypes.windll.winmm.waveOutSetVolume(0, 0xFFFFFFFF)
        return True
    except Exception as e:
        logger.debug(f"App volume: could not reset the channel volume: {e}")
        return False
