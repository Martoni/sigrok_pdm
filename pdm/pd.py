##
## This file is part of the libsigrokdecode project.
##
## Copyright (C) 2021 Fabien Marteau <fabien.marteau@armadeus.com>
##
## This program is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation; either version 2 of the License, or
## (at your option) any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with this program; if not, see <http://www.gnu.org/licenses/>.
##

import sigrokdecode as srd


class SamplerateError(Exception):
    pass


class Decoder(srd.Decoder):
    api_version = 3
    id = 'pdm'
    name = 'PDM'
    longname = 'Pulse Density Modulation'
    desc = 'Two-wire, delta sigma ADC raw output'
    license = 'gplv2+'
    inputs = ['logic']
    outputs = []
    tags = ['sound']
    channels = (
        {'id': 'clock', 'name': 'CLK', 'desc': 'Clock signal'},
        {'id': 'data', 'name': 'DATA', 'desc': 'Data signal'},
    )
    options = (
        {'id': 'polarity', 'desc': 'Polarity', 'default': 'clk-rising',
            'values': ('clk-rising', 'clk-falling')},

    )
    annotations = (
            ('left', 'Left Channel'),
            ('right', 'Right Channel'),
    )
    annotation_rows = (
            ('left', 'Left Channel', (0,)),
            ('right', 'Right Channel', (1,)),
    )
    binary = (
            ('raw', 'RAW file'),
    )

    def __init__(self):
        self.reset()

    def reset(self):
        self.samplerate = None
        self.ss_block = self.es_block = None

    def metadata(self, key, value):
        if key == srd.SRD_CONF_SAMPLERATE:
            self.samplerate = value

    def start(self):
        self.out_ann = self.register(srd.OUTPUT_ANN)
        self.out_binary = self.register(srd.OUTPUT_BINARY)
        self.out_average = \
            self.register(srd.OUTPUT_META,
                          meta=(float, 'Average', '?? TODO'))
    def putx(self, data):
        self.put(self.ss_block, self.es_block, self.out_ann, data)

    def putp(self, period_t):
        # Adjust granularity.
        if period_t == 0 or period_t >= 1:
            period_s = '%.1f s' % (period_t)
        elif period_t <= 1e-12:
            period_s = '%.1f fs' % (period_t * 1e15)
        elif period_t <= 1e-9:
            period_s = '%.1f ps' % (period_t * 1e12)
        elif period_t <= 1e-6:
            period_s = '%.1f ns' % (period_t * 1e9)
        elif period_t <= 1e-3:
            period_s = '%.1f μs' % (period_t * 1e6)
        else:
            period_s = '%.1f ms' % (period_t * 1e3)

        self.put(self.ss_block, self.es_block, self.out_ann, [1, [period_s]])

    def putb(self, data):
        self.put(self.ss_block, self.es_block, self.out_binary, data)

    def decode(self):
        if not self.samplerate:
            raise SamplerateError('Cannot decode without samplerate.')

        num_cycles = 0
        average = 0

        # Wait for an "active" edge (depends on config). This starts
        # the first full period of the inspected signal waveform.
        self.wait({0: 'f' if self.options['polarity'] == 'active-low' else 'r'})
        self.first_samplenum = self.samplenum

        # Keep getting samples for the period's middle and terminal edges.
        # At the same time that last sample starts the next period.
        while True:

            # Get the next two edges. Setup some variables that get
            # referenced in the calculation and in put() routines.
            start_samplenum = self.samplenum
            self.wait({0: 'e'})
            end_samplenum = self.samplenum
            self.wait({0: 'e'})
            self.ss_block = start_samplenum
            self.es_block = self.samplenum

            # Calculate the period, the duty cycle, and its ratio.
            period = self.samplenum - start_samplenum
            duty = end_samplenum - start_samplenum
            ratio = float(duty / period)

            # Report the duty cycle in percent.
            percent = float(ratio * 100)
            self.putx([0, ['%f%%' % percent]])

            # Report the duty cycle in the binary output.
            self.putb([0, bytes([int(ratio * 256)])])

            # Report the period in units of time.
            period_t = float(period / self.samplerate)
            self.putp(period_t)

            # Update and report the new duty cycle average.
            num_cycles += 1
            average += percent
            self.put(self.first_samplenum, self.es_block, self.out_average,
                     float(average / num_cycles))
