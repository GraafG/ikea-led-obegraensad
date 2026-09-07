#include "plugins/SplitClockPlugin.h"
#include <time.h>

static constexpr int BIG_NUMBER_HEIGHT = 7;
static constexpr int SPLIT_CLOCK_Y = (ROWS - BIG_NUMBER_HEIGHT) / 2;

void SplitClockPlugin::setup()
{
  Screen.clear();
  for (int x : {4, 5, 7, 8, 10, 11})
  {
    Screen.setPixel(x, 7, 1);
  }
  previousValue = -1;
  refreshTimer.forceReady();
  Serial.printf("%s: waiting for local time\n", getName());
}

void SplitClockPlugin::loop()
{
  if (!refreshTimer.isReady(250))
  {
    return;
  }

  // Read the NTP-maintained clock without getLocalTime's blocking sync timeout.
  const time_t now = time(nullptr);
  struct tm timeinfo = {};
  if (localtime_r(&now, &timeinfo) == nullptr || timeinfo.tm_year <= 116)
  {
    if (previousValue != -1)
    {
      setup();
    }
    return;
  }

  const int value = (mode == Mode::HOURS) ? timeinfo.tm_hour : timeinfo.tm_min;
  if (value != previousValue)
  {
    Screen.clear();
    Screen.drawBigNumbers(0, SPLIT_CLOCK_Y, {value / 10, value % 10});
    previousValue = value;
  }
}

const char *SplitClockPlugin::getName() const
{
  return mode == Mode::HOURS ? "Big Clock HH" : "Big Clock MM";
}
