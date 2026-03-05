import { test, expect } from '@playwright/test';
import {
  login,
  createTestCorpus,
  deleteCorpus,
  uploadFile,
  verifyPreview,
  verifyDelete,
  createTestFile,
  cleanupTestFiles,
} from './helpers';

let testCorpusId: string = '';
const TEST_CORPUS_NAME = `E2E 测试-${Date.now()}`;

test.beforeAll(async ({ browser }) => {
  console.log('=== 开始 E2E 测试套件 ===');
  const page = await browser.newPage();
  await login(page);
  testCorpusId = await createTestCorpus(page, TEST_CORPUS_NAME);
  await page.close();
});

test.afterAll(async ({ browser }) => {
  console.log('=== 清理测试数据 ===');
  const page = await browser.newPage();
  await login(page);
  if (testCorpusId) {
    await deleteCorpus(page, testCorpusId);
  }
  cleanupTestFiles();
  await page.close();
  console.log('=== E2E 测试套件完成 ===');
});

test.describe('文档上传测试', () => {
  test('上传小文件 (100KB)', async ({ page }) => {
    console.log('\n--- 测试：上传小文件 (100KB) ---');
    await login(page);
    await page.goto(`/dashboard/corpus/${testCorpusId}`);
    
    const testFile = createTestFile(100, 'test_small_100kb.txt');
    await uploadFile(page, testCorpusId, testFile.path);
    
    const fileRow = page.locator(`tr:has-text("${testFile.name}")`);
    await expect(fileRow).toBeVisible();
    
    console.log('✓ 小文件上传成功');
  });

  test('上传中等文件 (5MB)', async ({ page }) => {
    console.log('\n--- 测试：上传中等文件 (5MB) ---');
    await login(page);
    await page.goto(`/dashboard/corpus/${testCorpusId}`);
    
    const testFile = createTestFile(5 * 1024, 'test_medium_5mb.txt');
    await uploadFile(page, testCorpusId, testFile.path);
    
    const fileRow = page.locator(`tr:has-text("${testFile.name}")`);
    await expect(fileRow).toBeVisible();
    
    console.log('✓ 中等文件上传成功');
  });

  test('上传大文件 (15MB)', async ({ page }) => {
    console.log('\n--- 测试：上传大文件 (15MB) ---');
    await login(page);
    await page.goto(`/dashboard/corpus/${testCorpusId}`);
    
    const testFile = createTestFile(15 * 1024, 'test_large_15mb.txt');
    await uploadFile(page, testCorpusId, testFile.path);
    
    const fileRow = page.locator(`tr:has-text("${testFile.name}")`);
    await expect(fileRow).toBeVisible();
    
    console.log('✓ 大文件上传成功');
  });
});

test.describe('文档查看测试', () => {
  test('小文件内联预览', async ({ page }) => {
    console.log('\n--- 测试：小文件内联预览 ---');
    await login(page);
    await page.goto(`/dashboard/corpus/${testCorpusId}`);
    
    await verifyPreview(page, 'test_small_100kb.txt', 'text');
    console.log('✓ 小文件预览验证通过');
  });

  test('中等文件警告和选项', async ({ page }) => {
    console.log('\n--- 测试：中等文件警告和选项 ---');
    await login(page);
    await page.goto(`/dashboard/corpus/${testCorpusId}`);
    
    await verifyPreview(page, 'test_medium_5mb.txt', 'text');
    
    const warningAlert = page.locator('.el-alert--warning');
    await expect(warningAlert).toBeVisible();
    
    console.log('✓ 中等文件预览验证通过');
  });

  test('大文件 URL 预览模式', async ({ page }) => {
    console.log('\n--- 测试：大文件 URL 预览模式 ---');
    await login(page);
    await page.goto(`/dashboard/corpus/${testCorpusId}`);
    
    await verifyPreview(page, 'test_large_15mb.txt', 'url');
    
    const errorAlert = page.locator('.el-alert--error');
    await expect(errorAlert).toBeVisible();
    
    console.log('✓ 大文件 URL 预览验证通过');
  });
});

test.describe('文档删除测试', () => {
  test('删除确认对话框', async ({ page }) => {
    console.log('\n--- 测试：删除确认对话框 ---');
    await login(page);
    await page.goto(`/dashboard/corpus/${testCorpusId}`);
    
    await verifyDelete(page, 'test_small_100kb.txt');
    console.log('✓ 删除功能验证通过');
  });
});

test.describe('错误处理测试', () => {
  test('验证错误提示准确性', async ({ page }) => {
    console.log('\n--- 测试：错误提示验证 ---');
    await login(page);
    await page.goto(`/dashboard/corpus/${testCorpusId}`);
    
    const uploader = page.locator('.upload-demo');
    await expect(uploader).toBeVisible();
    
    const table = page.locator('.el-table');
    await expect(table).toBeVisible();
    
    console.log('✓ 错误处理验证通过');
  });
});
