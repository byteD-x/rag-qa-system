/**
 * 前端 API 测试 - 验证数据交互和错误处理
 * 使用 Jest 测试框架
 */

// 模拟 fetch API
global.fetch = jest.fn() as unknown as typeof fetch;
global.localStorage = {
    getItem: jest.fn(),
    setItem: jest.fn(),
    removeItem: jest.fn(),
    length: 0,
    clear: jest.fn(),
    key: jest.fn()
} as unknown as Storage;

import { sendMessageStream, type SSEEvent } from './chat';

describe('Frontend API Integration Tests', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        (global.localStorage.getItem as jest.Mock).mockReturnValue('test-token');
    });

    describe('sendMessageStream - Success Cases', () => {
        it('should handle successful stream response', async () => {
            // 模拟 SSE 流式响应
            const mockStream = {
                getReader: () => ({
                    read: jest.fn()
                        .mockResolvedValueOnce({
                            done: false,
                            value: new TextEncoder().encode('data: {"type":"sentence","data":{"text":"Hello"}}\n\n')
                        })
                        .mockResolvedValueOnce({
                            done: false,
                            value: new TextEncoder().encode('data: {"type":"done"}\n\n')
                        })
                        .mockResolvedValueOnce({ done: true, value: undefined })
                })
            };

            (global.fetch as jest.Mock).mockResolvedValue({
                ok: true,
                body: mockStream
            });

            const stream = sendMessageStream('session-123', {
                question: 'Test question',
                scope: {
                    mode: 'single',
                    corpus_ids: ['corpus-1'],
                    allow_common_knowledge: true
                }
            });

            const results: SSEEvent[] = [];
            for await (const event of stream) {
                results.push(event);
            }

            expect(results).toHaveLength(2);
            expect(results[0]?.type).toBe('sentence');
            expect(results[1]?.type).toBe('done');
        });

        it('should handle [DONE] marker', async () => {
            const mockStream = {
                getReader: () => ({
                    read: jest.fn()
                        .mockResolvedValueOnce({
                            done: false,
                            value: new TextEncoder().encode('data: [DONE]\n\n')
                        })
                        .mockResolvedValueOnce({ done: true, value: undefined })
                })
            };

            (global.fetch as jest.Mock).mockResolvedValue({
                ok: true,
                body: mockStream
            });

            const stream = sendMessageStream('session-123', {
                question: 'Test',
                scope: { mode: 'single', corpus_ids: [], allow_common_knowledge: true }
            });

            const results: SSEEvent[] = [];
            for await (const event of stream) {
                results.push(event);
            }

            expect(results).toHaveLength(1);
            expect(results[0]?.type).toBe('done');
        });
    });

    describe('sendMessageStream - Error Cases', () => {
        it('should handle HTTP error response', async () => {
            (global.fetch as jest.Mock).mockResolvedValue({
                ok: false,
                json: async () => ({ error: 'Unauthorized' })
            });

            const stream = sendMessageStream('session-123', {
                question: 'Test',
                scope: { mode: 'single', corpus_ids: [], allow_common_knowledge: true }
            });

            await expect(async () => {
                for await (const _ of stream) {
                    // Should throw
                }
            }).rejects.toThrow('Unauthorized');
        });

        it('should handle network error with retry', async () => {
            // 第一次调用失败，第二次成功
            (global.fetch as jest.Mock)
                .mockRejectedValueOnce(new Error('Network error'))
                .mockResolvedValueOnce({
                    ok: true,
                    body: {
                        getReader: () => ({
                            read: jest.fn()
                                .mockResolvedValueOnce({
                                    done: false,
                                    value: new TextEncoder().encode('data: {"type":"done"}\n\n')
                                })
                                .mockResolvedValueOnce({ done: true, value: undefined })
                        })
                    }
                });

            const stream = sendMessageStream(
                'session-123',
                {
                    question: 'Test',
                    scope: { mode: 'single', corpus_ids: [], allow_common_knowledge: true }
                },
                3, // maxRetries
                10  // initialRetryDelay (ms for testing)
            );

            const results: SSEEvent[] = [];
            for await (const event of stream) {
                results.push(event);
            }

            // 应该重试成功
            expect(results).toHaveLength(1);
            expect(results[0]?.type).toBe('done');
            expect(global.fetch).toHaveBeenCalledTimes(2); // 重试一次
        });

        it('should handle max retries exceeded', async () => {
            // 持续失败
            (global.fetch as jest.Mock).mockRejectedValue(new Error('Network error'));

            const stream = sendMessageStream(
                'session-123',
                {
                    question: 'Test',
                    scope: { mode: 'single', corpus_ids: [], allow_common_knowledge: true }
                },
                2, // maxRetries
                10 // initialRetryDelay
            );

            await expect(async () => {
                for await (const _ of stream) {
                    // Should throw after retries
                }
            }).rejects.toThrow('已重试 2 次');
        });
    });

    describe('sendMessageStream - Retry Logic', () => {
        it('should use exponential backoff', async () => {
            const setTimeoutSpy = jest.spyOn(global, 'setTimeout')
                .mockImplementation((cb: any) => {
                    cb();
                    return 0 as any;
                });

            (global.fetch as jest.Mock).mockRejectedValue(new Error('Network error'));

            const stream = sendMessageStream(
                'session-123',
                {
                    question: 'Test',
                    scope: { mode: 'single', corpus_ids: [], allow_common_knowledge: true }
                },
                3,
                100
            );

            try {
                for await (const _ of stream) {
                    // Ignore
                }
            } catch (e) {
                // Expected
            }

            // 验证指数退避：100ms, 200ms, 400ms
            expect(setTimeoutSpy).toHaveBeenCalledTimes(3);
            expect(setTimeoutSpy).toHaveBeenNthCalledWith(1, expect.any(Function), 100);
            expect(setTimeoutSpy).toHaveBeenNthCalledWith(2, expect.any(Function), 200);
            expect(setTimeoutSpy).toHaveBeenNthCalledWith(3, expect.any(Function), 400);

            setTimeoutSpy.mockRestore();
        });
    });
});
