import { ref } from 'vue';
import { getUploadUrl, uploadToS3, notifyUploadComplete, getIngestJob } from '@/api/documents';
import { ElMessage } from 'element-plus';

export function useUploader(corpusId: string, onSuccess?: () => void) {
    const isUploading = ref(false);
    const uploadProgress = ref(0);
    const isPolling = ref(false);
    const pollingProgress = ref(0);
    const currentStatus = ref('');

    let pollerId: any = null;

    async function uploadFile(file: File) {
        if (file.size > 500 * 1024 * 1024) {
            ElMessage.error('文件不能超过 500MB');
            return;
        }

        try {
            isUploading.value = true;
            uploadProgress.value = 0;
            currentStatus.value = '申请签名...';

            // 1. 获取预签名 URL
            const ext = file.name.split('.').pop()?.toLowerCase() || 'txt';
            const urlRes: any = await getUploadUrl({
                corpus_id: corpusId,
                file_name: file.name,
                file_type: ext,
                size_bytes: file.size
            });

            // 2. 直传 S3
            currentStatus.value = '上传中...';
            await uploadToS3(urlRes.upload_url, file, (percent) => {
                uploadProgress.value = percent;
            });

            // 3. 提交网关
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
                ElMessage.success('上传成功，无索引任务返回');
                reset();
            }

        } catch (err: any) {
            ElMessage.error('上传流程失败');
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
                    currentStatus.value = job.status === 'queued' ? '排队中...' : '处理中...';
                }
            } catch (err) {
                console.error('任务轮询错误:', err);
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
    }

    return {
        uploadFile,
        isUploading,
        uploadProgress,
        isPolling,
        pollingProgress,
        currentStatus
    };
}
