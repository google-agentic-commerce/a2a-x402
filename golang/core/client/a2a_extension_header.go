package client

import (
	"context"

	"github.com/a2aproject/a2a-go/a2aclient"
)

type extensionHeaderInterceptor struct {
	a2aclient.PassthroughInterceptor
	extensionURIs []string
}

func newExtensionHeaderInterceptor(extensionURIs []string) *extensionHeaderInterceptor {
	return &extensionHeaderInterceptor{
		extensionURIs: extensionURIs,
	}
}

func (i *extensionHeaderInterceptor) Before(ctx context.Context, req *a2aclient.Request) (context.Context, error) {
	if req.Meta == nil {
		req.Meta = make(a2aclient.CallMeta)
	}
	req.Meta["X-A2A-Extensions"] = i.extensionURIs
	return ctx, nil
}
