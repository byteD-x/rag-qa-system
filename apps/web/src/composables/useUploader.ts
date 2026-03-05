import { ref } from 'vue';
import { getUploadUrl, uploadToS3, notifyUploadComplete, getIngestJob } from '@/api/documents';
import { ElMessage } from 'element-plus';

export interface UploadError {
    type: 'file_too_large' | 'timeout' | 'network_error' | 'server_error' | 'unknown';
    message: string;
    statusCode?: number;
    details?: string;
}

export interface UploadProgress {
    percent: number;
    loaded: number;
    total: number;
    estimatedRemaining?: number;
}

export function useUploader(corpusId: string, onSuccess?: () => void) {
    const isUploading = ref(false);
    const uploadProgress = ref(0);
    const isPolling = ref(false);
    const pollingProgress = ref(0);
    const currentStatus = ref('');
    const uploadError = ref<UploadError | null>(null);
    const progressInfo = ref<UploadProgress | null>(null);

    let pollerId: any = null;
    let uploadStartTime = 0;

    const MAX_FILE_SIZE = 500 * 1024 * 1024;
    const MAX_RETRIES = 3;
    const RETRY_DELAY = 1000;

    function classifyError(err: any, fileSize: number): UploadError {
        const statusCode = err?.response?.status || err?.status;
        
        if (statusCode === 413 || err?.code === 'ERR_REQUEST_TOO_LARGE') {
            return {
                type: 'file_too_large',
                message: '文件过大',
                statusCode: 413,
                details: `当前文件大小为 ${formatBytes(fileSize)}，超过服务器限制`
            };
        }

        if (err?.code === 'ECONNABORTED' || err?.message?.includes('timeout')) {
            return {
                type: 'timeout',
                message: '请求超时',
                details: '上传时间过长，请检查网络连接或稍后重试'
            };
        }

        if (err?.code === 'NETWORK_ERROR' || err?.message?.includes('Network Error') || !navigator.onLine) {
            return {
                type: 'network_error',
                message: '网络错误',
                details: '请检查网络连接后重试'
            };
        }

        if (statusCode && statusCode >= 500) {
            return {
                type: 'server_error',
                message: '服务器错误',
                statusCode,
                details: `服务器返回错误 (${statusCode})，请稍后重试`
            };
        }

        if (statusCode === 401) {
            return {
                type: 'server_error',
                message: '认证失败',
                statusCode: 401,
                details: '登录已过期，请刷新页面后重试'
            };
        }

        if (statusCode === 403) {
            return {
                type: 'server_error',
                message: '权限不足',
                statusCode: 403,
                details: '没有上传权限，请联系管理员'
            };
        }

        return {
            type: 'unknown',
            message: '上传失败',
            statusCode,
            details: err?.message || '未知错误'
        };
    }

    function formatBytes(bytes: number): string {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    function formatTime(seconds: number): string {
        if (seconds < 60) return `${Math.round(seconds)}秒`;
        if (seconds < 3600) return `${Math.round(seconds / 60)}分钟`;
        return `${Math.round(seconds / 3600)}小时`;
    }

    function logError(error: UploadError, fileName: string, fileSize: number) {
        const timestamp = new Date().toISOString();
        console.group(`[Upload Error] ${timestamp}`);
        console.error('文件:', fileName);
        console.error('文件大小:', formatBytes(fileSize));
        console.error('错误类型:', error.type);
        console.error('错误信息:', error.message);
        console.error('状态码:', error.statusCode);
        console.error('详细信息:', error.details);
        console.error('原始错误:', error);
        console.groupEnd();
    }

    function calculateProgress(loaded: number, total: number): UploadProgress {
        const percent = Math.round((loaded * 100) / total);
        const elapsed = (Date.now() - uploadStartTime) / 1000;
        const bytesPerSecond = loaded / elapsed;
        const remaining = total - loaded;
        const estimatedRemaining = bytesPerSecond > 0 ? remaining / bytesPerSecond : undefined;

        return {
            percent,
            loaded,
            total,
            estimatedRemaining
        };
    }

    async function uploadWithRetry(file: File, maxRetries: number): Promise<void> {
        let lastError: any = null;
        
        for (let attempt = 1; attempt <= maxRetries; attempt++) {
            try {
                currentStatus.value = `上传中... (尝试 ${attempt}/${maxRetries})`;
                await uploadToS3(urlRes.upload_url, file, (loaded, total) => {
                    const progress = calculateProgress(loaded, total);
                    uploadProgress.value = progress.percent;
                    progressInfo.value = progress;
                });
                return;
            } catch (err: any) {
                lastError = err;
                if (attempt < maxRetries) {
                    console.warn(`上传失败，${RETRY_DELAY / 1000}秒后重试 (${attempt}/${maxRetries})`, err);
                    await new Promise(resolve => setTimeout(resolve, RETRY_DELAY));
                }
            }
        }
        
        throw lastError;
    }

    let urlRes: any = null;

    async function uploadFile(file: File) {
        uploadError.value = null;
        progressInfo.value = null;
        
        if (file.size > MAX_FILE_SIZE) {
            const error: UploadError = {
                type: 'file_too_large',
                message: '文件超过限制',
                statusCode: 413,
                details: `文件大小 ${formatBytes(file.size)} 超过最大限制 ${formatBytes(MAX_FILE_SIZE)}`
            };
            ElMessage.error(error.details);
            logError(error, file.name, file.size);
            uploadError.value = error;
            return;
        }

        try {
            isUploading.value = true;
            uploadProgress.value = 0;
            uploadStartTime = Date.now();
            currentStatus.value = '申请签名...';

            const ext = file.name.split('.').pop()?.toLowerCase() || 'txt';
            urlRes = await getUploadUrl({
                corpus_id: corpusId,
                file_name: file.name,
                file_type: ext,
                size_bytes: file.size
            });

            currentStatus.value = '上传中...';
            await uploadWithRetry(file, MAX_RETRIES);

            currentStatus.value = '通知网关入库...';
            const notifyRes: any = await notifyUploadComplete({
                corpus_id: corpusId,
                storage_key: urlRes.storage_key,
                file_name: file.name,
                file_type: ext,
                size_bytes: file.size
            });

            if (notifyRes.job_id) {
                startPolling(notifyRes.job_id);
            } else {
                ElMessage.success('上传成功');
                reset();
            }

        } catch (err: any) {
            const error = classifyError(err, file.size);
            uploadError.value = error;
            logError(error, file.name, file.size);

            let userMessage = error.message;
            if (error.details) {
                userMessage += `: ${error.details}`;
            }

            ElMessage({
                message: userMessage,
                type: 'error',
                duration: 5000,
                showClose: true
            });

            reset();
        }
    }

    function startPolling(jobId: string) {
        isUploading.value = false;
        isPolling.value = true;
        pollingProgress.value = 0;
        currentStatus.value = '等待解析切片处理...';

        pollerId = setInterval(async () => {
            try {
                const job: any = await getIngestJob(jobId);
                pollingProgress.value = job.progress || 0;

                if (job.status === 'done') {
                    ElMessage.success('文档处理完成');
                    clearPolling();
                    if (onSuccess) onSuccess();
                } else if (job.status === 'failed') {
                    ElMessage.error('文档处理失败');
                    clearPolling();
                } else {
                    const statusMap: Record<string, string> = {
                        'queued': '排队中...',
                        'running': '处理中...',
                        'pending': '等待中...'
                    };
                    currentStatus.value = statusMap[job.status] || `状态：${job.status}`;
                }
            } catch (err: any) {
                console.error('任务轮询错误:', err);
                ElMessage.error('获取任务状态失败');
                clearPolling();
            }
        }, 2000);
    }

    function clearPolling() {
        if (pollerId) clearInterval(pollerId);
        reset();
    }

    function reset() {
        isUploading.value = false;
        isPolling.value = false;
        uploadProgress.value = 0;
        pollingProgress.value = 0;
        currentStatus.value = '';
        uploadError.value = null;
        progressInfo.value = null;
    }

    function getProgressText(): string {
        if (!progressInfo.value) {
            return `${uploadProgress.value}%`;
        }
        const { loaded, total, estimatedRemaining } = progressInfo.value;
        let text = `${formatBytes(loaded)} / ${formatBytes(total)} (${uploadProgress.value}%)`;
        if (estimatedRemaining !== undefined) {
            text += ` · 剩余 ${formatTime(estimatedRemaining)}`;
        }
        return text;
    }

    function retryUpload(file: File) {
        if (file) {
            uploadFile(file);
        }
    }

    return {
        uploadFile,
        retryUpload,
        isUploading,
        uploadProgress,
        isPolling,
        pollingProgress,
        currentStatus,
        uploadError,
        progressInfo,
        getProgressText
    };
}
