#pragma once

#include "PluginManager.h"
#include "timing.h"

class SplitClockPlugin : public Plugin
{
public:
  enum class Mode
  {
    HOURS,
    MINUTES
  };

private:
  const Mode mode;
  int previousValue = -1;
  NonBlockingDelay refreshTimer;

public:
  explicit SplitClockPlugin(Mode mode) : mode(mode)
  {
  }

  void setup() override;
  void loop() override;
  const char *getName() const override;
};
