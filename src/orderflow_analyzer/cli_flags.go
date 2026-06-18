package main

import (
	"strconv"
	"strings"
)

type multiFlag []string

func (m *multiFlag) String() string { return strings.Join(*m, ",") }
func (m *multiFlag) Set(v string) error {
	*m = append(*m, v)
	return nil
}

type multiIntFlag []int

func (m *multiIntFlag) String() string {
	parts := make([]string, len(*m))
	for i, v := range *m {
		parts[i] = strconv.Itoa(v)
	}
	return strings.Join(parts, ",")
}
func (m *multiIntFlag) Set(v string) error {
	n, err := strconv.Atoi(v)
	if err != nil {
		return err
	}
	*m = append(*m, n)
	return nil
}

type multiFloatFlag []float64

func (m *multiFloatFlag) String() string {
	parts := make([]string, len(*m))
	for i, v := range *m {
		parts[i] = strconv.FormatFloat(v, 'f', -1, 64)
	}
	return strings.Join(parts, ",")
}
func (m *multiFloatFlag) Set(v string) error {
	n, err := strconv.ParseFloat(v, 64)
	if err != nil {
		return err
	}
	*m = append(*m, n)
	return nil
}
