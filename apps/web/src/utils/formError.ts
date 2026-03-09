/**
 * 自定义表单错误提示组件
 * 提供更友好的错误提示体验，包含动画和图标
 */

import { ElMessage } from 'element-plus';

export interface FormErrorOptions {
  message: string;
  duration?: number;
  type?: 'error' | 'warning';
}

/**
 * 显示增强的表单错误提示
 */
export function showFormError(options: FormErrorOptions | string) {
  const config = typeof options === 'string' 
    ? { message: options }
    : options;

  const {
    message,
    duration = 3000,
    type = 'error'
  } = config;

  ElMessage({
    message,
    type,
    duration,
    showClose: true,
    customClass: 'custom-form-error'
  });
}

/**
 * 验证表单字段并显示错误
 */
export function validateField(
  value: any,
  rules: Array<{
    required?: boolean;
    pattern?: RegExp;
    validator?: (value: any) => boolean;
    message: string;
  }>
): string | null {
  for (const rule of rules) {
    if (rule.required && !value) {
      return rule.message;
    }
    
    if (rule.pattern && !rule.pattern.test(value)) {
      return rule.message;
    }
    
    if (rule.validator && !rule.validator(value)) {
      return rule.message;
    }
  }
  
  return null;
}

/**
 * 验证邮箱格式
 */
export function validateEmail(email: string): string | null {
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailRegex.test(email)) {
    return '请输入有效的邮箱地址';
  }
  return null;
}

/**
 * 验证密码强度
 */
export function validatePassword(password: string): string | null {
  if (password.length < 8) {
    return '密码长度至少 8 位';
  }
  
  const hasUpperCase = /[A-Z]/.test(password);
  const hasLowerCase = /[a-z]/.test(password);
  const hasNumbers = /\d/.test(password);
  const hasSpecialChar = /[!@#$%^&*(),.?":{}|<>]/.test(password);
  
  const validCount = [hasUpperCase, hasLowerCase, hasNumbers, hasSpecialChar].filter(Boolean).length;
  
  if (validCount < 2) {
    return '密码需包含大写字母、小写字母、数字或特殊字符中的至少两种';
  }
  
  return null;
}
