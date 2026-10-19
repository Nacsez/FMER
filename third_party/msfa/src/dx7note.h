/*
 * Copyright 2012 Google Inc.
 * 
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 * 
 *      http://www.apache.org/licenses/LICENSE-2.0
 * 
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#ifndef SYNTH_DX7NOTE_H_
#define SYNTH_DX7NOTE_H_

// This is the logic to put together a note from the MIDI description
// and run the low-level modules.

// It will continue to evolve a bit, as note-stealing logic, scaling,
// and real-time control of parameters live here.

#include "env.h"
#include "pitchenv.h"
#include "fm_core.h"

class Dx7Note {
 public:
  // FMER: correct the historical declaration; implementation reads VCED.
  void init(const char patch[156], int midinote, int velocity);

  // Note: this _adds_ to the buffer. Interesting question whether it's
  // worth it...
  void compute(int32_t *buf, int32_t lfo_val, int32_t lfo_delay,
    const Controllers *ctrls);

  void keyup();
  // FMER portamento: Q24 log2-frequency delta on ratio operators only.
  // The caller supplies the retained note snapshot. Fixed oscillators, phase,
  // envelopes, feedback and key/velocity scaling remain unchanged.
  void shift_ratio_pitch(int32_t delta, const char patch[156]);
  // FMER: all envelopes must complete; nonzero release levels remain active.
  bool finished() const {
    for (int op = 0; op < 6; ++op) if (!env_[op].finished()) return false;
    return true;
  }

  // TODO: parameter changes

  // TODO: some way of indicating end-of-note. Maybe should be a return
  // value from the compute method? (Having a count return from keyup
  // is also tempting, but if there's a dynamic parameter change after
  // keyup, that won't work.

 private:
  FmCore core_;
  Env env_[6];
  FmOpParams params_[6];
  PitchEnv pitchenv_;
  int32_t basepitch_[6];
  int32_t fb_buf_[2];
  int32_t fb_shift_;

  int algorithm_;
  int pitchmoddepth_;
  int pitchmodsens_;
  // FMER original AMD/AMS curve: maximum log2 attenuation per operator, Q24.
  // Kept in the note snapshot; no allocation or transcendental audio work.
  int32_t ampmoddepth_[6];
};

#endif  // SYNTH_DX7NOTE_H_
