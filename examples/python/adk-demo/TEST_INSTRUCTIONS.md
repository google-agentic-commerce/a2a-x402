# Testing the EigenDA Storage System

## Quick Test Scenarios

### 1. Basic Storage Test
```
User: Store this text: "Hello EigenDA!"
[System should request payment of $0.01]
User: yes
[System should confirm storage and provide certificate]
```

### 2. Retrieval Test
```
User: Get the text with certificate [use certificate from step 1]
[System should retrieve and display "Hello EigenDA!"]
```

### 3. List Certificates Test
```
User: Show me my stored certificates
[System should list all stored certificates]
```

## Common Issues and Solutions

### Issue: "State inconsistency: 'purchase_task' not found"
**Cause**: The agent tried to approve payment without first making a storage request.
**Solution**: Fixed by:
1. Handling multiple approval keywords ("yes", "approve", "confirm")
2. Returning friendly error message when no pending payment exists
3. Clearing state properly after task completion

### Issue: Agent doesn't recognize the EigenDA agent
**Cause**: Client still pointing to merchant_agent
**Solution**: Updated `agent.py` to point to `eigenda_agent`

### Issue: Payment flow confusion
**Cause**: Instructions weren't clear about the two-step process
**Solution**: Updated instructions to explicitly describe:
1. First send storage request
2. Wait for payment confirmation request
3. Then send approval

## Testing Checklist

- [ ] Server starts and initializes EigenDA Docker container
- [ ] Client connects to EigenDA agent successfully
- [ ] Client introduces itself as EigenDA storage assistant
- [ ] Storage request triggers payment flow
- [ ] Payment approval works with "yes" or "approve"
- [ ] Certificate is returned after successful storage
- [ ] Retrieval using certificate works
- [ ] List certificates shows stored items
- [ ] State is properly cleared after transactions

## Debug Commands

Check if EigenDA is running:
```bash
docker ps | grep eigenda-proxy
```

View EigenDA logs:
```bash
docker logs eigenda-proxy
```

Test EigenDA health:
```bash
curl http://localhost:3100/health
```

Check agent availability:
```bash
curl http://localhost:10000/agents/eigenda_agent/.well-known/agent-card.json
```