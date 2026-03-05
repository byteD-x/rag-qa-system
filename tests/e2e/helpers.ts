import { Page, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

export interface TestFile {
  path: string;
  name: string;
  size: number;
  sizeCategory: 'small' | 'medium' | 'large';
}

/**
 * 创建测试文件
 */
export function createTestFile(sizeKB: number, name: string): TestFile {
  const testFilesDir = path.join(process.cwd(), 'tests', 'e2e', 'fixtures');
  if (!fs.existsSync(testFilesDir)) {
    fs.mkdirSync(testFilesDir, { recursive: true });
  }

  const filePath = path.join(testFilesDir, name);
  const sizeBytes = sizeKB * 1024;
  
  const line = '这是一行测试内容，用于填充文件大小。RAG 系统文档测试。\n';
  const lineBytes = Buffer.byteLength(line, 'utf8');
  const linesNeeded = Math.ceil(sizeBytes / lineBytes);
  
  let content = '';
  for (let i = 0; i < linesNeeded; i++) {
    content += `第 ${i + 1} 行：${line}`;
  }
  
  const buffer = Buffer.from(content, 'utf8');
  const finalBuffer = buffer.slice(0, sizeBytes);
  
  fs.writeFileSync(filePath, finalBuffer);
  
  const actualSize = fs.statSync(filePath).size;
  let sizeCategory: 'small' | 'medium' | 'large';
  if (sizeKB < 1024) {
    sizeCategory = 'small';
  } else if (sizeKB < 10 * 1024) {
    sizeCategory = 'medium';
  } else {
    sizeCategory = 'large';
  }

  console.log(`创建测试文件：${name}, 大小：${(actualSize / 1024 / 1024).toFixed(2)}MB, 类别：${sizeCategory}`);
  
  return {
    path: filePath,
    name,
    size: actualSize,
    sizeCategory,
  };
}

/**
 * 清理测试文件
 */
export function cleanupTestFiles() {
  const testFilesDir = path.join(process.cwd(), 'tests', 'e2e', 'fixtures');
  if (fs.existsSync(testFilesDir)) {
    fs.rmSync(testFilesDir, { recursive: true, force: true });
  }
}

/**
 * 登录到系统
 */
export async function login(page: Page) {
  await page.goto('/');
  await page.waitForSelector('input[type="email"], input[type="text"]', { state: 'visible' });
  await page.fill('input[type="email"], input[type="text"]', 'admin@local');
  await page.fill('input[type="password"]', 'ChangeMe123!');
  await page.click('button[type="submit"]');
  await page.waitForURL(/\/dashboard/);
  console.log('登录成功');
}

/**
 * 创建测试语料库
 */
export async function createTestCorpus(page: Page, name: string): Promise<string> {
  await page.goto('/dashboard/corpora');
  await page.waitForSelector('.new-corpus-btn', { state: 'visible' });
  await page.click('.new-corpus-btn');
  
  await page.waitForSelector('input[placeholder*="名称"]', { state: 'visible' });
  const nameInput = page.locator('input[placeholder*="名称"]').first();
  await nameInput.fill(name);
  
  const descInput = page.locator('textarea[placeholder*="描述"]').first();
  if (await descInput.isVisible()) {
    await descInput.fill(`测试语料库：${name}`);
  }
  
  const createButton = page.locator('button:has-text("创建"), button:has-text("确定")').first();
  await createButton.click();
  
  await page.waitForSelector('.el-message--success', { state: 'visible', timeout: 10000 });
  await page.waitForTimeout(1000);
  
  const corpusLink = page.locator(`text=${name}`).first();
  await corpusLink.waitFor({ state: 'visible' });
  await corpusLink.click();
  
  await page.waitForURL(/\/corpus\/[^/]+/);
  const url = page.url();
  const corpusId = url.split('/').pop() || '';
  
  console.log(`创建语料库成功：${name}, ID: ${corpusId}`);
  
  return corpusId;
}

/**
 * 删除语料库
 */
export async function deleteCorpus(page: Page, corpusId: string) {
  try {
    await page.goto('/dashboard/corpora');
    await page.waitForTimeout(1000);
    
    const deleteBtn = page.locator(`tr:has-text("${corpusId}") button:has-text("删除")`).first();
    if (await deleteBtn.isVisible()) {
      await deleteBtn.click();
      await page.waitForSelector('.el-message-box', { state: 'visible' });
      const confirmBtn = page.locator('.el-message-box__footer button:has-text("删除"), button:has-text("确定")').last();
      await confirmBtn.click();
      await page.waitForSelector('.el-message--success', { state: 'visible', timeout: 10000 });
      console.log(`删除语料库成功：${corpusId}`);
    }
  } catch (error) {
    console.log(`删除语料库失败或不存在：${corpusId}`, error);
  }
}

/**
 * 上传文件到语料库
 */
export async function uploadFile(page: Page, corpusId: string, filePath: string) {
  const fileName = path.basename(filePath);
  const fileSize = fs.statSync(filePath).size;
  
  console.log(`开始上传文件：${fileName}, 大小：${(fileSize / 1024 / 1024).toFixed(2)}MB`);
  
  await page.goto(`/dashboard/corpus/${corpusId}`);
  await page.waitForSelector('.upload-demo', { state: 'visible' });
  
  const fileInput = page.locator('input[type="file"]');
  await fileInput.setInputFiles(filePath);
  
  await page.waitForSelector('.progress-container', { state: 'visible', timeout: 15000 });
  await page.waitForSelector('.el-message--success', { state: 'visible', timeout: 120000 });
  
  console.log(`文件上传成功：${fileName}`);
  await page.waitForTimeout(2000);
}

/**
 * 验证文档预览
 */
export async function verifyPreview(page: Page, fileName: string, expectedMode: 'text' | 'url') {
  const previewBtn = page.locator(`tr:has-text("${fileName}") button:has-text("在线查看")`).first();
  await previewBtn.click();
  
  await page.waitForSelector('.el-dialog', { state: 'visible' });
  
  if (expectedMode === 'text') {
    await page.waitForSelector('textarea.el-textarea__inner', { state: 'visible', timeout: 10000 });
    console.log('验证成功：文本预览模式');
  } else {
    await page.waitForSelector('iframe.preview-frame', { state: 'visible', timeout: 10000 });
    console.log('验证成功：URL 预览模式');
  }
  
  const closeBtn = page.locator('.el-dialog__header .el-dialog__close').first();
  await closeBtn.click();
}

/**
 * 验证删除功能
 */
export async function verifyDelete(page: Page, fileName: string) {
  const deleteBtn = page.locator(`tr:has-text("${fileName}") button:has-text("删除")`).first();
  await deleteBtn.click();
  
  await page.waitForSelector('.el-dialog', { state: 'visible' });
  
  const dialogContent = page.locator('.el-dialog');
  await expect(dialogContent).toContainText('删除');
  await expect(dialogContent).toContainText(fileName);
  
  console.log('验证成功：删除确认对话框显示正确');
  
  const confirmBtn = page.locator('.el-dialog__footer button:has-text("确认删除"), button:has-text("确定")').last();
  await confirmBtn.click();
  
  await page.waitForSelector('.el-message--success', { state: 'visible', timeout: 10000 });
  
  const deletedDoc = page.locator(`tr:has-text("${fileName}")`);
  await expect(deletedDoc).not.toBeVisible();
  
  console.log('验证成功：文档已删除');
}
