#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <mmsystem.h>

#include <cstdarg>
#include <cstdio>
#include <cstring>

namespace {

HMODULE g_real_winmm = nullptr;
char g_log_path[MAX_PATH] = {};
char g_module_dir[MAX_PATH] = {};

constexpr uintptr_t kDrawCharacterAddress = 0x00425D90;
constexpr uintptr_t kMeasureStringAddress = 0x00426CC7;
constexpr uintptr_t kFontRecordsAddress = 0x004A7930;
constexpr int kFontRecordSize = 24;
constexpr unsigned char kHangulLeadFirst = 0x80;
constexpr unsigned char kHangulLeadLast = 0x98;
constexpr unsigned char kHangulTrailFirst = 0xA0;
constexpr int kHangulTrailCount = 96;
constexpr int kHangulGlyphCount = 2350;
constexpr int kDynamicGlyphSlot = 0x7F;

using DrawCharacterFn = void (__cdecl *)(int, int);
DrawCharacterFn g_original_draw_character = nullptr;
unsigned char* g_draw_trampoline = nullptr;
using MeasureStringFn = short (__cdecl *)(const char*, int);
MeasureStringFn g_original_measure_string = nullptr;
unsigned char* g_measure_trampoline = nullptr;
unsigned char g_hangul_font[kHangulGlyphCount * 8] = {};
bool g_hangul_font_loaded = false;
int g_pending_lead = -1;
LONG g_rendered_hangul_count = 0;

using TimeGetSystemTimeFn = MMRESULT (WINAPI *)(LPMMTIME, UINT);
using MciSendStringAFn = MCIERROR (WINAPI *)(LPCSTR, LPSTR, UINT, HWND);
using TimeEndPeriodFn = MMRESULT (WINAPI *)(UINT);
using TimeBeginPeriodFn = MMRESULT (WINAPI *)(UINT);
using TimeGetTimeFn = DWORD (WINAPI *)();
using SndPlaySoundAFn = BOOL (WINAPI *)(LPCSTR, UINT);
using PlaySoundWFn = BOOL (WINAPI *)(LPCWSTR, HMODULE, DWORD);
using MciSendCommandAFn = MCIERROR (WINAPI *)(MCIDEVICEID, UINT, DWORD_PTR, DWORD_PTR);
using MciGetErrorStringAFn = BOOL (WINAPI *)(MCIERROR, LPSTR, UINT);

TimeGetSystemTimeFn p_timeGetSystemTime = nullptr;
MciSendStringAFn p_mciSendStringA = nullptr;
TimeEndPeriodFn p_timeEndPeriod = nullptr;
TimeBeginPeriodFn p_timeBeginPeriod = nullptr;
TimeGetTimeFn p_timeGetTime = nullptr;
SndPlaySoundAFn p_sndPlaySoundA = nullptr;
PlaySoundWFn p_PlaySoundW = nullptr;
MciSendCommandAFn p_mciSendCommandA = nullptr;
MciGetErrorStringAFn p_mciGetErrorStringA = nullptr;

void WriteLog(const char* format, ...) {
  if (!g_log_path[0]) return;
  FILE* file = nullptr;
  if (fopen_s(&file, g_log_path, "a") != 0 || !file) return;

  SYSTEMTIME now{};
  GetLocalTime(&now);
  std::fprintf(file, "%04u-%02u-%02u %02u:%02u:%02u.%03u ",
               now.wYear, now.wMonth, now.wDay,
               now.wHour, now.wMinute, now.wSecond, now.wMilliseconds);
  va_list args;
  va_start(args, format);
  std::vfprintf(file, format, args);
  va_end(args);
  std::fputc('\n', file);
  std::fclose(file);
}

template <typename T>
bool Resolve(T& target, const char* name) {
  target = reinterpret_cast<T>(GetProcAddress(g_real_winmm, name));
  if (!target) WriteLog("GetProcAddress failed: %s error=%lu", name, GetLastError());
  return target != nullptr;
}

bool LoadRealWinmm() {
  char system_path[MAX_PATH] = {};
  const UINT length = GetSystemDirectoryA(system_path, MAX_PATH);
  if (!length || length >= MAX_PATH - 11) return false;
  lstrcatA(system_path, "\\winmm.dll");

  g_real_winmm = LoadLibraryA(system_path);
  if (!g_real_winmm) {
    WriteLog("LoadLibrary failed: %s error=%lu", system_path, GetLastError());
    return false;
  }

  bool ok = true;
  ok &= Resolve(p_timeGetSystemTime, "timeGetSystemTime");
  ok &= Resolve(p_mciSendStringA, "mciSendStringA");
  ok &= Resolve(p_timeEndPeriod, "timeEndPeriod");
  ok &= Resolve(p_timeBeginPeriod, "timeBeginPeriod");
  ok &= Resolve(p_timeGetTime, "timeGetTime");
  ok &= Resolve(p_sndPlaySoundA, "sndPlaySoundA");
  ok &= Resolve(p_PlaySoundW, "PlaySoundW");
  ok &= Resolve(p_mciSendCommandA, "mciSendCommandA");
  ok &= Resolve(p_mciGetErrorStringA, "mciGetErrorStringA");
  return ok;
}

bool IsWizardProcess() {
  char path[MAX_PATH] = {};
  if (!GetModuleFileNameA(nullptr, path, MAX_PATH)) return false;
  const char* name = std::strrchr(path, '\\');
  name = name ? name + 1 : path;
  return _stricmp(name, "WIZARD.EXE") == 0 ||
         _stricmp(name, "WIZARD_900.EXE") == 0;
}

void InitializeLogPath(HMODULE module) {
  char path[MAX_PATH] = {};
  if (!GetModuleFileNameA(module, path, MAX_PATH)) return;
  char* slash = std::strrchr(path, '\\');
  if (!slash) return;
  slash[1] = '\0';
  lstrcpynA(g_module_dir, path, MAX_PATH);
  lstrcpynA(g_log_path, path, MAX_PATH);
  lstrcatA(g_log_path, "wizardry7_korean.log");
}

bool LoadHangulFont() {
  char path[MAX_PATH] = {};
  lstrcpynA(path, g_module_dir, MAX_PATH);
  lstrcatA(path, "wizardry7_ksx1001_8x8.bin");
  FILE* file = nullptr;
  if (fopen_s(&file, path, "rb") != 0 || !file) {
    WriteLog("Hangul font not found: %s", path);
    return false;
  }
  const size_t read = std::fread(g_hangul_font, 1, sizeof(g_hangul_font), file);
  std::fclose(file);
  if (read != sizeof(g_hangul_font)) {
    WriteLog("Hangul font size mismatch: expected=%zu actual=%zu", sizeof(g_hangul_font), read);
    return false;
  }
  WriteLog("Hangul font loaded: %s glyphs=%d", path, kHangulGlyphCount);
  return true;
}

void SetBitmapBit(unsigned char* bitmap, int bytes_per_row, int x, int y) {
  bitmap[y * bytes_per_row + x / 8] |= static_cast<unsigned char>(0x80u >> (x & 7));
}

bool InstallGlyphInDynamicSlot(int font_index, int glyph_index) {
  if (!g_hangul_font_loaded || glyph_index < 0 || glyph_index >= kHangulGlyphCount) return false;
  if (font_index < 0 || font_index >= 8) return false;

  const uintptr_t record = kFontRecordsAddress + font_index * kFontRecordSize;
  auto* header = *reinterpret_cast<unsigned char**>(record + 12);
  auto* first_plane = *reinterpret_cast<unsigned char**>(record + 16);
  auto* second_plane = *reinterpret_cast<unsigned char**>(record + 20);
  if (!header || !first_plane) return false;

  const int width = header[0];
  const int height = header[1];
  const int bytes_per_row = header[3];
  const int glyph_count = header[5];
  const int first_size = *reinterpret_cast<unsigned short*>(header + 10);
  const int second_size = *reinterpret_cast<unsigned short*>(header + 14);
  if (kDynamicGlyphSlot >= glyph_count || width <= 0 || height <= 0 || bytes_per_row <= 0 || first_size <= 0) return false;

  unsigned char* first = first_plane + kDynamicGlyphSlot * first_size;
  std::memset(first, 0, first_size);
  unsigned char* second = nullptr;
  if (second_plane && second_size > 0) {
    second = second_plane + kDynamicGlyphSlot * second_size;
    std::memset(second, 0, second_size);
  }

  const int target_width = width < 8 ? width : 8;
  const int target_height = height < 8 ? height : 8;
  const int x_offset = (width - target_width) / 2;
  const int y_offset = (height - target_height) / 2;
  const unsigned char* source = g_hangul_font + glyph_index * 8;

  for (int y = 0; y < target_height; ++y) {
    const int source_y = y * 8 / target_height;
    for (int x = 0; x < target_width; ++x) {
      const int source_x = x * 8 / target_width;
      if ((source[source_y] & (0x80u >> source_x)) == 0) continue;
      SetBitmapBit(first, bytes_per_row, x_offset + x, y_offset + y);
      if (second) SetBitmapBit(second, bytes_per_row, x_offset + x, y_offset + y);
    }
  }

  header[0x10 + kDynamicGlyphSlot * 2] = kDynamicGlyphSlot;
  const int extra_spacing = static_cast<signed char>(header[7]);
  int table_width = target_width - extra_spacing;
  if (table_width < 1) table_width = 1;
  if (table_width > 255) table_width = 255;
  header[0x11 + kDynamicGlyphSlot * 2] = static_cast<unsigned char>(table_width);
  return true;
}

void __cdecl DrawCharacterHook(int character, int font_index) {
  const unsigned char value = static_cast<unsigned char>(character);
  if (value >= kHangulLeadFirst && value <= kHangulLeadLast) {
    g_pending_lead = value;
    return;
  }

  if (g_pending_lead >= 0) {
    const int lead = g_pending_lead;
    g_pending_lead = -1;
    if (value >= kHangulTrailFirst) {
      const int glyph_index = (lead - kHangulLeadFirst) * kHangulTrailCount + (value - kHangulTrailFirst);
      if (InstallGlyphInDynamicSlot(font_index, glyph_index)) {
        const LONG count = InterlockedIncrement(&g_rendered_hangul_count);
        if (count <= 20) WriteLog("Rendered Hangul glyph: index=%d font=%d", glyph_index, font_index);
        g_original_draw_character(kDynamicGlyphSlot, font_index);
        return;
      }
    }
  }

  g_original_draw_character(character, font_index);
}

bool ContainsHangulCode(const unsigned char* text) {
  if (!text) return false;
  for (size_t index = 0; text[index]; ++index) {
    if (text[index] >= kHangulLeadFirst && text[index] <= kHangulLeadLast &&
        text[index + 1] >= kHangulTrailFirst) {
      return true;
    }
  }
  return false;
}

short __cdecl MeasureStringHook(const char* string, int font_index) {
  const auto* text = reinterpret_cast<const unsigned char*>(string);
  if (!ContainsHangulCode(text) || font_index < 0 || font_index >= 8) {
    return g_original_measure_string(string, font_index);
  }

  const uintptr_t record = kFontRecordsAddress + font_index * kFontRecordSize;
  auto* header = *reinterpret_cast<unsigned char**>(record + 12);
  if (!header || header[5] == 0) return g_original_measure_string(string, font_index);

  const int glyph_count = header[5];
  const int extra_spacing = static_cast<signed char>(header[7]);
  int width = 0;
  for (size_t index = 0; text[index]; ++index) {
    const unsigned char value = text[index];
    if (value >= kHangulLeadFirst && value <= kHangulLeadLast &&
        text[index + 1] >= kHangulTrailFirst) {
      width += header[0] < 8 ? header[0] : 8;
      ++index;
      continue;
    }
    const int glyph = value % glyph_count;
    width += header[0x11 + glyph * 2] + extra_spacing;
  }
  return static_cast<short>(width);
}

bool InstallDrawHook() {
  auto* target = reinterpret_cast<unsigned char*>(kDrawCharacterAddress);
  constexpr unsigned char expected[6] = {0x55, 0x8B, 0xEC, 0x83, 0xEC, 0x6C};
  if (std::memcmp(target, expected, sizeof(expected)) != 0) {
    WriteLog("Draw hook signature mismatch at %p", target);
    return false;
  }

  g_draw_trampoline = static_cast<unsigned char*>(VirtualAlloc(nullptr, 16, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE));
  if (!g_draw_trampoline) {
    WriteLog("VirtualAlloc for draw trampoline failed: error=%lu", GetLastError());
    return false;
  }
  std::memcpy(g_draw_trampoline, target, 6);
  g_draw_trampoline[6] = 0xE9;
  *reinterpret_cast<int*>(g_draw_trampoline + 7) = static_cast<int>((target + 6) - (g_draw_trampoline + 11));
  g_original_draw_character = reinterpret_cast<DrawCharacterFn>(g_draw_trampoline);

  DWORD old_protection = 0;
  if (!VirtualProtect(target, 6, PAGE_EXECUTE_READWRITE, &old_protection)) {
    WriteLog("VirtualProtect for draw hook failed: error=%lu", GetLastError());
    return false;
  }
  target[0] = 0xE9;
  *reinterpret_cast<int*>(target + 1) = static_cast<int>(reinterpret_cast<unsigned char*>(&DrawCharacterHook) - (target + 5));
  target[5] = 0x90;
  FlushInstructionCache(GetCurrentProcess(), target, 6);
  DWORD ignored = 0;
  VirtualProtect(target, 6, old_protection, &ignored);
  WriteLog("Draw hook installed: target=%p trampoline=%p", target, g_draw_trampoline);
  return true;
}

bool InstallMeasureHook() {
  auto* target = reinterpret_cast<unsigned char*>(kMeasureStringAddress);
  constexpr unsigned char expected[6] = {0x55, 0x8B, 0xEC, 0x83, 0xEC, 0x14};
  if (std::memcmp(target, expected, sizeof(expected)) != 0) {
    WriteLog("Measure hook signature mismatch at %p", target);
    return false;
  }

  g_measure_trampoline = static_cast<unsigned char*>(VirtualAlloc(nullptr, 16, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE));
  if (!g_measure_trampoline) {
    WriteLog("VirtualAlloc for measure trampoline failed: error=%lu", GetLastError());
    return false;
  }
  std::memcpy(g_measure_trampoline, target, 6);
  g_measure_trampoline[6] = 0xE9;
  *reinterpret_cast<int*>(g_measure_trampoline + 7) = static_cast<int>((target + 6) - (g_measure_trampoline + 11));
  g_original_measure_string = reinterpret_cast<MeasureStringFn>(g_measure_trampoline);

  DWORD old_protection = 0;
  if (!VirtualProtect(target, 6, PAGE_EXECUTE_READWRITE, &old_protection)) {
    WriteLog("VirtualProtect for measure hook failed: error=%lu", GetLastError());
    return false;
  }
  target[0] = 0xE9;
  *reinterpret_cast<int*>(target + 1) = static_cast<int>(reinterpret_cast<unsigned char*>(&MeasureStringHook) - (target + 5));
  target[5] = 0x90;
  FlushInstructionCache(GetCurrentProcess(), target, 6);
  DWORD ignored = 0;
  VirtualProtect(target, 6, old_protection, &ignored);
  WriteLog("Measure hook installed: target=%p trampoline=%p", target, g_measure_trampoline);
  return true;
}

}  // namespace

extern "C" {

__declspec(dllexport) MMRESULT WINAPI timeGetSystemTime(LPMMTIME time, UINT size) {
  return p_timeGetSystemTime ? p_timeGetSystemTime(time, size) : MMSYSERR_ERROR;
}

__declspec(dllexport) MCIERROR WINAPI mciSendStringA(LPCSTR command, LPSTR result, UINT length, HWND callback) {
  return p_mciSendStringA ? p_mciSendStringA(command, result, length, callback) : MCIERR_HARDWARE;
}

__declspec(dllexport) MMRESULT WINAPI timeEndPeriod(UINT period) {
  return p_timeEndPeriod ? p_timeEndPeriod(period) : MMSYSERR_ERROR;
}

__declspec(dllexport) MMRESULT WINAPI timeBeginPeriod(UINT period) {
  return p_timeBeginPeriod ? p_timeBeginPeriod(period) : MMSYSERR_ERROR;
}

__declspec(dllexport) DWORD WINAPI timeGetTime() {
  return p_timeGetTime ? p_timeGetTime() : GetTickCount();
}

__declspec(dllexport) BOOL WINAPI sndPlaySoundA(LPCSTR sound, UINT flags) {
  return p_sndPlaySoundA ? p_sndPlaySoundA(sound, flags) : FALSE;
}

__declspec(dllexport) BOOL WINAPI PlaySoundW(LPCWSTR sound, HMODULE module, DWORD flags) {
  return p_PlaySoundW ? p_PlaySoundW(sound, module, flags) : FALSE;
}

__declspec(dllexport) MCIERROR WINAPI mciSendCommandA(MCIDEVICEID device, UINT message, DWORD_PTR flags, DWORD_PTR parameters) {
  return p_mciSendCommandA ? p_mciSendCommandA(device, message, flags, parameters) : MCIERR_HARDWARE;
}

__declspec(dllexport) BOOL WINAPI mciGetErrorStringA(MCIERROR error, LPSTR text, UINT length) {
  return p_mciGetErrorStringA ? p_mciGetErrorStringA(error, text, length) : FALSE;
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID) {
  if (reason == DLL_PROCESS_ATTACH) {
    DisableThreadLibraryCalls(instance);
    InitializeLogPath(instance);
    const bool loaded = LoadRealWinmm();
    WriteLog("Wizardry 7 Korean proxy loaded: real_winmm=%p resolved=%s", g_real_winmm, loaded ? "yes" : "no");
    if (IsWizardProcess()) {
      g_hangul_font_loaded = LoadHangulFont();
      InstallDrawHook();
      InstallMeasureHook();
    } else {
      WriteLog("Forwarding-only mode for non-game process");
    }
  } else if (reason == DLL_PROCESS_DETACH) {
    WriteLog("Wizardry 7 Korean proxy unloaded");
    if (g_real_winmm) FreeLibrary(g_real_winmm);
  }
  return TRUE;
}

}  // extern "C"
