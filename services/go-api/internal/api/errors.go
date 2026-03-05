package api

import (
	"errors"
	"fmt"
	"net/http"
)

// APIError represents a structured API error
type APIError struct {
	Code       string `json:"code"`
	Message    string `json:"message"`
	Detail     string `json:"detail,omitempty"`
	StatusCode int    `json:"-"`
}

func (e *APIError) Error() string {
	if e.Detail != "" {
		return fmt.Sprintf("%s: %s", e.Message, e.Detail)
	}
	return e.Message
}

// Standard error codes
const (
	ErrCodeInternal      = "INTERNAL_ERROR"
	ErrCodeNotFound      = "NOT_FOUND"
	ErrCodeInvalidInput  = "INVALID_INPUT"
	ErrCodeUnauthorized  = "UNAUTHORIZED"
	ErrCodeForbidden     = "FORBIDDEN"
	ErrCodeConflict      = "CONFLICT"
	ErrCodeServiceUnavailable = "SERVICE_UNAVAILABLE"
)

// Predefined errors
var (
	ErrInternal      = &APIError{Code: ErrCodeInternal, Message: "Internal server error", StatusCode: http.StatusInternalServerError}
	ErrNotFound      = &APIError{Code: ErrCodeNotFound, Message: "Resource not found", StatusCode: http.StatusNotFound}
	ErrInvalidInput  = &APIError{Code: ErrCodeInvalidInput, Message: "Invalid input", StatusCode: http.StatusBadRequest}
	ErrUnauthorized  = &APIError{Code: ErrCodeUnauthorized, Message: "Unauthorized", StatusCode: http.StatusUnauthorized}
	ErrForbidden     = &APIError{Code: ErrCodeForbidden, Message: "Forbidden", StatusCode: http.StatusForbidden}
	ErrConflict      = &APIError{Code: ErrCodeConflict, Message: "Resource conflict", StatusCode: http.StatusConflict}
	ErrServiceUnavailable = &APIError{Code: ErrCodeServiceUnavailable, Message: "Service unavailable", StatusCode: http.StatusServiceUnavailable}
)

// Error helpers
func NewAPIError(code string, message string, statusCode int) *APIError {
	return &APIError{
		Code:       code,
		Message:    message,
		StatusCode: statusCode,
	}
}

func NewInvalidInputError(message string) *APIError {
	return &APIError{
		Code:       ErrCodeInvalidInput,
		Message:    message,
		StatusCode: http.StatusBadRequest,
	}
}

func NewNotFoundError(resource string) *APIError {
	return &APIError{
		Code:       ErrCodeNotFound,
		Message:    fmt.Sprintf("%s not found", resource),
		StatusCode: http.StatusNotFound,
	}
}

func WrapError(err error, message string) error {
	if err == nil {
		return nil
	}
	return fmt.Errorf("%s: %w", message, err)
}

// IsAPIError checks if an error is an APIError
func IsAPIError(err error) bool {
	var apiErr *APIError
	return errors.As(err, &apiErr)
}

// GetAPIError extracts APIError from error or returns internal error
func GetAPIError(err error) *APIError {
	if err == nil {
		return nil
	}
	var apiErr *APIError
	if errors.As(err, &apiErr) {
		return apiErr
	}
	return ErrInternal
}
