package api

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime"
	"net"
	"net/http"
	"net/url"
	"strconv"
	"strings"
)

const (
	maxSuccessBody = 1 << 20
	maxErrorBody   = 64 << 10
)

type Doer interface {
	Do(*http.Request) (*http.Response, error)
}

type ErrorKind string

const (
	ErrorValidation ErrorKind = "validation"
	ErrorAuth       ErrorKind = "authentication"
	ErrorNetwork    ErrorKind = "network"
	ErrorServer     ErrorKind = "server"
	ErrorProtocol   ErrorKind = "protocol"
)

type Error struct {
	Kind              ErrorKind
	StatusCode        int
	Code              string
	Message           string
	RequestID         string
	Retryable         bool
	RetryAfterSeconds int
	Err               error
}

func (e *Error) Error() string {
	if e.Message != "" {
		return e.Message
	}
	if e.Err != nil {
		return e.Err.Error()
	}
	return "CiteGuild request failed"
}

func (e *Error) Unwrap() error { return e.Err }

type SearchRequest struct {
	Query           string   `json:"query"`
	Limit           int      `json:"limit"`
	Language        string   `json:"language,omitempty"`
	ExcludedDomains []string `json:"excluded_domains,omitempty"`
}

type SearchResponse struct {
	ContractVersion string         `json:"contract_version"`
	Results         []SearchResult `json:"results"`
}

type SearchResult struct {
	ArticleID    string  `json:"article_id"`
	Title        string  `json:"title"`
	CanonicalURL string  `json:"canonical_url"`
	Domain       string  `json:"domain"`
	Excerpt      string  `json:"excerpt"`
	Relevance    float64 `json:"relevance"`
	Language     string  `json:"language"`
	LastSeenAt   string  `json:"last_seen_at"`
}

type Client struct {
	http      Doer
	baseURL   *url.URL
	apiKey    string
	userAgent string
}

func NewClient(httpClient Doer, baseURL, apiKey, userAgent string) (*Client, error) {
	parsed, err := parseBaseURL(baseURL)
	if err != nil {
		return nil, err
	}

	return &Client{
		http:      httpClient,
		baseURL:   parsed,
		apiKey:    apiKey,
		userAgent: userAgent,
	}, nil
}

func ValidateBaseURL(baseURL string) error {
	_, err := parseBaseURL(baseURL)
	return err
}

func parseBaseURL(baseURL string) (*url.URL, error) {
	parsed, err := url.Parse(baseURL)
	if err != nil {
		return nil, errors.New("API base URL is invalid")
	}
	if (parsed.Scheme != "http" && parsed.Scheme != "https") || parsed.Host == "" {
		return nil, errors.New("API base URL must be an absolute HTTP(S) URL")
	}
	if parsed.User != nil || parsed.RawQuery != "" || parsed.Fragment != "" {
		return nil, errors.New("API base URL must not contain credentials, a query, or a fragment")
	}
	if parsed.Scheme == "http" {
		host := parsed.Hostname()
		ip := net.ParseIP(host)
		if host != "localhost" && (ip == nil || !ip.IsLoopback()) {
			return nil, errors.New("API base URL must use HTTPS except for loopback development")
		}
	}
	parsed.Path = strings.TrimRight(parsed.Path, "/")
	return parsed, nil
}

func (c *Client) Search(ctx context.Context, input SearchRequest) (SearchResponse, error) {
	body, err := json.Marshal(input)
	if err != nil {
		return SearchResponse{}, fmt.Errorf("encode search request: %w", err)
	}

	responseBody, err := c.do(ctx, http.MethodPost, "/v1/search", bytes.NewReader(body))
	if err != nil {
		return SearchResponse{}, err
	}

	var result SearchResponse
	if err := decodeJSON(responseBody, &result); err != nil {
		return SearchResponse{}, &Error{
			Kind:    ErrorProtocol,
			Message: "CiteGuild returned an invalid search response; try again or contact support",
			Err:     err,
		}
	}
	if result.ContractVersion != "v1" {
		return SearchResponse{}, &Error{
			Kind:    ErrorProtocol,
			Message: "CiteGuild returned an unsupported search contract version; update the CLI",
		}
	}
	if result.Results == nil {
		result.Results = []SearchResult{}
	}
	return result, nil
}

func (c *Client) CheckAuth(ctx context.Context) error {
	_, err := c.do(ctx, http.MethodGet, "/v1/account", nil)
	return err
}

func (c *Client) do(ctx context.Context, method, path string, body io.Reader) ([]byte, error) {
	requestURL := *c.baseURL
	requestURL.Path = strings.TrimRight(requestURL.Path, "/") + path

	req, err := http.NewRequestWithContext(ctx, method, requestURL.String(), body)
	if err != nil {
		return nil, fmt.Errorf("create request: %w", err)
	}
	req.Header.Set("Accept", "application/json")
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	if c.apiKey != "" {
		req.Header.Set("Authorization", "Bearer "+c.apiKey)
	}
	if c.userAgent != "" {
		req.Header.Set("User-Agent", c.userAgent)
	}

	resp, err := c.http.Do(req)
	if err != nil {
		return nil, classifyTransportError(ctx, err)
	}
	defer resp.Body.Close()

	limit := int64(maxSuccessBody)
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		limit = maxErrorBody
	}
	responseBody, err := readBounded(resp.Body, limit)
	if err != nil {
		return nil, &Error{
			Kind:       ErrorProtocol,
			StatusCode: resp.StatusCode,
			Message:    "CiteGuild returned a response that could not be read safely",
			Err:        err,
		}
	}

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, classifyStatusError(resp.StatusCode, resp.Header, responseBody, c.apiKey)
	}
	if err := requireJSON(resp.Header.Get("Content-Type")); err != nil {
		return nil, &Error{
			Kind:       ErrorProtocol,
			StatusCode: resp.StatusCode,
			Message:    "CiteGuild returned a non-JSON response",
			Err:        err,
		}
	}
	return responseBody, nil
}

func classifyTransportError(ctx context.Context, err error) error {
	if cause := context.Cause(ctx); cause != nil {
		return &Error{Kind: ErrorNetwork, Message: "CiteGuild request canceled or timed out", Err: cause}
	}
	return &Error{Kind: ErrorNetwork, Message: "Could not connect to CiteGuild; check the API URL and network", Err: err}
}

func classifyStatusError(status int, headers http.Header, body []byte, apiKey string) error {
	var payload struct {
		Code      string `json:"code"`
		Message   string `json:"message"`
		RequestID string `json:"request_id"`
		Retryable bool   `json:"retryable"`
	}
	_ = decodeJSON(body, &payload)
	if payload.RequestID == "" {
		payload.RequestID = headers.Get("X-Request-ID")
	}
	if payload.Message == "" {
		payload.Message = http.StatusText(status)
	}
	if apiKey != "" {
		payload.Message = strings.ReplaceAll(payload.Message, apiKey, "[REDACTED]")
		payload.RequestID = strings.ReplaceAll(payload.RequestID, apiKey, "[REDACTED]")
	}
	retryAfterSeconds := 0
	if status == http.StatusTooManyRequests {
		if seconds, err := strconv.Atoi(headers.Get("Retry-After")); err == nil && seconds >= 0 && seconds <= 86_400 {
			retryAfterSeconds = seconds
		}
	}

	kind := ErrorServer
	switch status {
	case http.StatusBadRequest, http.StatusUnprocessableEntity:
		kind = ErrorValidation
	case http.StatusUnauthorized, http.StatusForbidden:
		kind = ErrorAuth
	}
	return &Error{
		Kind:              kind,
		StatusCode:        status,
		Code:              payload.Code,
		Message:           payload.Message,
		RequestID:         payload.RequestID,
		Retryable:         payload.Retryable,
		RetryAfterSeconds: retryAfterSeconds,
	}
}

func requireJSON(contentType string) error {
	mediaType, _, err := mime.ParseMediaType(contentType)
	if err != nil {
		return err
	}
	if mediaType != "application/json" && !strings.HasSuffix(mediaType, "+json") {
		return fmt.Errorf("unexpected content type %q", mediaType)
	}
	return nil
}

func readBounded(reader io.Reader, limit int64) ([]byte, error) {
	body, err := io.ReadAll(io.LimitReader(reader, limit+1))
	if err != nil {
		return nil, err
	}
	if int64(len(body)) > limit {
		return nil, fmt.Errorf("response exceeds %d bytes", limit)
	}
	return body, nil
}

func decodeJSON(body []byte, target any) error {
	decoder := json.NewDecoder(bytes.NewReader(body))
	if err := decoder.Decode(target); err != nil {
		return err
	}
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		if err == nil {
			return errors.New("response contains multiple JSON values")
		}
		return err
	}
	return nil
}
