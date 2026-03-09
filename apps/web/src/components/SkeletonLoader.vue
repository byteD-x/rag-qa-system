<template>
  <div class="skeleton-loader" :class="[variant, { animated }]" :style="customStyles">
    <template v-if="variant === 'text'">
      <div class="skeleton-text" :style="textStyle"></div>
    </template>
    
    <template v-else-if="variant === 'circular'">
      <div class="skeleton-circle" :style="circleStyle"></div>
    </template>
    
    <template v-else-if="variant === 'rect'">
      <div class="skeleton-rect glass-panel" :style="rectStyle"></div>
    </template>
    
    <template v-else-if="variant === 'rounded'">
      <div class="skeleton-rounded glass-panel" :style="roundedStyle"></div>
    </template>
    
    <template v-else-if="variant === 'card'">
      <div class="skeleton-card glass-panel">
        <div class="skeleton-card-image"></div>
        <div class="skeleton-card-content">
          <div class="skeleton-card-title"></div>
          <div class="skeleton-card-text"></div>
          <div class="skeleton-card-text short"></div>
        </div>
      </div>
    </template>
    
    <template v-else-if="variant === 'list'">
      <div class="skeleton-list">
        <div v-for="i in (count || 3)" :key="i" class="skeleton-list-item glass-panel">
          <div class="skeleton-list-avatar"></div>
          <div class="skeleton-list-content">
            <div class="skeleton-list-title"></div>
            <div class="skeleton-list-text"></div>
          </div>
        </div>
      </div>
    </template>
    
    <template v-else-if="variant === 'table'">
      <div class="skeleton-table glass-panel">
        <div v-for="i in (count || 5)" :key="i" class="skeleton-table-row">
          <div class="skeleton-table-cell" v-for="j in (columns || 4)" :key="j"></div>
        </div>
      </div>
    </template>
    
    <template v-else-if="variant === 'chat'">
      <div class="skeleton-chat">
        <div class="skeleton-chat-message user">
          <div class="skeleton-chat-avatar"></div>
          <div class="skeleton-chat-bubble">
            <div class="skeleton-chat-line"></div>
            <div class="skeleton-chat-line short"></div>
          </div>
        </div>
        <div class="skeleton-chat-message assistant">
          <div class="skeleton-chat-avatar"></div>
          <div class="skeleton-chat-bubble">
            <div class="skeleton-chat-line"></div>
            <div class="skeleton-chat-line"></div>
            <div class="skeleton-chat-line short"></div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

interface Props {
  variant?: 'text' | 'circular' | 'rect' | 'rounded' | 'card' | 'list' | 'table' | 'chat';
  width?: string | number;
  height?: string | number;
  borderRadius?: string | number;
  count?: number;
  columns?: number;
  animated?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'text',
  count: 3,
  columns: 4,
  animated: true
});

const customStyles = computed(() => ({
  width: props.width ? (typeof props.width === 'number' ? `${props.width}px` : props.width) : undefined,
  height: props.height ? (typeof props.height === 'number' ? `${props.height}px` : props.height) : undefined
}));

const textStyle = computed(() => ({
  width: props.width ? (typeof props.width === 'number' ? `${props.width}px` : props.width) : '100%',
  height: props.height ? (typeof props.height === 'number' ? `${props.height}px` : props.height) : '1em'
}));

const circleStyle = computed(() => ({
  width: props.width ? (typeof props.width === 'number' ? `${props.width}px` : props.width) : (props.height || '40px'),
  height: props.height ? (typeof props.height === 'number' ? `${props.height}px` : props.height) : (props.width || '40px'),
  borderRadius: '50%'
}));

const rectStyle = computed(() => ({
  width: props.width ? (typeof props.width === 'number' ? `${props.width}px` : props.width) : '100%',
  height: props.height ? (typeof props.height === 'number' ? `${props.height}px` : props.height) : '200px',
  borderRadius: props.borderRadius ? (typeof props.borderRadius === 'number' ? `${props.borderRadius}px` : props.borderRadius) : 'var(--radius-md)'
}));

const roundedStyle = computed(() => ({
  width: props.width ? (typeof props.width === 'number' ? `${props.width}px` : props.width) : '100%',
  height: props.height ? (typeof props.height === 'number' ? `${props.height}px` : props.height) : '60px',
  borderRadius: props.borderRadius ? (typeof props.borderRadius === 'number' ? `${props.borderRadius}px` : props.borderRadius) : 'var(--radius-md)'
}));
</script>

<style scoped>
.skeleton-loader {
  display: inline-block;
  position: relative;
  overflow: hidden;
  border-radius: inherit;
}

/* Base block color logic */
.skeleton-loader :deep(div[class^="skeleton-"]:not(.skeleton-loader):not(.glass-panel):not(.skeleton-card-content):not(.skeleton-list-content):not(.skeleton-table-row):not(.skeleton-chat):not(.skeleton-chat-message):not(.skeleton-list)) {
  background-color: var(--border-color);
}

.skeleton-loader.animated :deep(div[class^="skeleton-"]:not(.skeleton-loader):not(.glass-panel):not(.skeleton-card-content):not(.skeleton-list-content):not(.skeleton-table-row):not(.skeleton-chat):not(.skeleton-chat-message):not(.skeleton-list)) {
  background: linear-gradient(
    90deg,
    var(--border-color) 25%,
    var(--border-strong) 37%,
    var(--border-color) 63%
  );
  background-size: 400% 100%;
  animation: ant-skeleton-loading 1.4s ease infinite;
}

@keyframes ant-skeleton-loading {
  0% {
    background-position: 100% 50%;
  }
  100% {
    background-position: 0 50%;
  }
}

/* Text variant */
.skeleton-text {
  border-radius: var(--radius-xs);
}

/* Circular variant */
.skeleton-circle {
  border-radius: 50%;
}

/* Rect variant */
.skeleton-rect, .skeleton-rounded {
  position: relative;
}

/* Card variant */
.skeleton-card {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 20px;
  border-radius: var(--radius-lg);
}

.skeleton-card-image {
  width: 100%;
  height: 160px;
  border-radius: var(--radius-md);
}

.skeleton-card-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.skeleton-card-title {
  width: 50%;
  height: 24px;
  border-radius: var(--radius-xs);
}

.skeleton-card-text {
  width: 100%;
  height: 16px;
  border-radius: 4px;
}

.skeleton-card-text.short {
  width: 70%;
}

/* List variant */
.skeleton-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.skeleton-list-item {
  display: flex;
  gap: 16px;
  align-items: center;
  padding: 16px;
  border-radius: var(--radius-md);
}

.skeleton-list-avatar {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  flex-shrink: 0;
}

.skeleton-list-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.skeleton-list-title {
  width: 40%;
  height: 18px;
  border-radius: 4px;
}

.skeleton-list-text {
  width: 80%;
  height: 14px;
  border-radius: 4px;
}

/* Table variant */
.skeleton-table {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  border-radius: var(--radius-md);
}

.skeleton-table-row {
  display: flex;
  gap: 12px;
}

.skeleton-table-cell {
  flex: 1;
  height: 32px;
  border-radius: var(--radius-sm);
}

/* Chat variant */
.skeleton-chat {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.skeleton-chat-message {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

.skeleton-chat-message.user {
  flex-direction: row-reverse;
}

.skeleton-chat-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  flex-shrink: 0;
}

.skeleton-chat-bubble {
  flex: 1;
  max-width: 60%;
  padding: 16px 20px;
  border-radius: var(--radius-lg);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.skeleton-chat-message.assistant .skeleton-chat-bubble {
  border-top-left-radius: 4px;
}

.skeleton-chat-message.user .skeleton-chat-bubble {
  border-top-right-radius: 4px;
  background-color: rgba(37, 99, 235, 0.1) !important;
}

.skeleton-loader.animated .skeleton-chat-message.user .skeleton-chat-bubble {
  background: linear-gradient(
    90deg,
    rgba(37, 99, 235, 0.1) 25%,
    rgba(37, 99, 235, 0.2) 37%,
    rgba(37, 99, 235, 0.1) 63%
  ) !important;
  background-size: 400% 100% !important;
  animation: ant-skeleton-loading 1.4s ease infinite;
}

.skeleton-chat-line {
  width: 100%;
  height: 14px;
  border-radius: 4px;
  background: rgba(255,255,255,0.4) !important;
}

.skeleton-chat-line.short {
  width: 65%;
}
</style>