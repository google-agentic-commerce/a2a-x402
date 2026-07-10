// Copyright 2025 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     https://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package utils

import (
	"testing"
)

func TestToMap(t *testing.T) {
	tests := []struct {
		name    string
		input   interface{}
		wantErr bool
	}{
		{
			name:    "valid struct",
			input:   map[string]string{"key": "value"},
			wantErr: false,
		},
		{
			name:    "nil input",
			input:   nil,
			wantErr: true,
		},
		{
			name: "valid struct with nested data",
			input: struct {
				Name  string
				Value int
			}{"test", 42},
			wantErr: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result, err := ToMap(tt.input)
			if (err != nil) != tt.wantErr {
				t.Errorf("ToMap() error = %v, wantErr %v", err, tt.wantErr)
				return
			}
			if !tt.wantErr && result == nil {
				t.Error("ToMap() returned nil result for valid input")
			}
		})
	}
}

func TestFromMap(t *testing.T) {
	tests := []struct {
		name    string
		input   map[string]interface{}
		target  interface{}
		wantErr bool
	}{
		{
			name:  "valid map",
			input: map[string]interface{}{"name": "test", "value": 42},
			target: &struct {
				Name  string
				Value int
			}{},
			wantErr: false,
		},
		{
			name:    "nil map",
			input:   nil,
			target:  &struct{ Name string }{},
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := FromMap(tt.input, tt.target)
			if (err != nil) != tt.wantErr {
				t.Errorf("FromMap() error = %v, wantErr %v", err, tt.wantErr)
			}
		})
	}
}

func TestToSlice(t *testing.T) {
	tests := []struct {
		name    string
		input   interface{}
		wantErr bool
	}{
		{
			name:    "valid slice",
			input:   []string{"a", "b", "c"},
			wantErr: false,
		},
		{
			name:    "nil input",
			input:   nil,
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result, err := ToSlice(tt.input)
			if (err != nil) != tt.wantErr {
				t.Errorf("ToSlice() error = %v, wantErr %v", err, tt.wantErr)
				return
			}
			if !tt.wantErr && result == nil {
				t.Error("ToSlice() returned nil result for valid input")
			}
		})
	}
}
