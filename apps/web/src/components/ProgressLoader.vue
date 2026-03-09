<template>
  <div class="progress-loader-wrapper">
    <div class="progress-loader tech-glow" :style="{ width: `${size}px`, height: `${size}px` }">
      <svg class="spinner" viewBox="0 0 100 100">
        <!-- Background circle -->
        <circle
          class="progress-ring-bg"
          cx="50"
          cy="50"
          :r="radius"
          :stroke-width="strokeWidth"
        />
        
        <!-- Animated filling circle -->
        <circle
          class="progress-ring"
          cx="50"
          cy="50"
          :r="radius"
          :stroke-width="strokeWidth"
          :style="{ strokeDashoffset: strokeDashoffset, stroke: color }"
        />
        
        <!-- Rotating tech outer ring -->
        <circle
          v-if="techStyle"
          class="tech-ring"
          cx="50"
          cy="50"
          :r="radius + 4"
          :stroke-width="1"
          stroke="rgba(59, 130, 246, 0.4)"
          stroke-dasharray="10 15"
        />
        <!-- Inner ring -->
        <circle
          v-if="techStyle"
          class="tech-ring reverse"
          cx="50"
          cy="50"
          :r="radius - 4"
          :stroke-width="1"
          stroke="rgba(59, 130, 246, 0.3)"
          stroke-dasharray="5 20"
        />
      </svg>
      <div class="progress-content">
        <span v-if="showPercentage" class="progress-text" :style="{ fontSize: textFontSize, color: color }">
          {{ percentage }}<span class="percent-sign">%</span>
        </span>
        <slot></slot>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

interface Props {
  percentage?: number;
  size?: number;
  strokeWidth?: number;
  showPercentage?: boolean;
  color?: string;
  techStyle?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  percentage: 0,
  size: 100,
  strokeWidth: 6,
  showPercentage: true,
  color: 'var(--blue-600)',
  techStyle: true
});

const radius = computed(() => 50 - props.strokeWidth - (props.techStyle ? 5 : 0));
const circumference = computed(() => 2 * Math.PI * radius.value);

const strokeDashoffset = computed(() => {
  const clampedPercentage = Math.max(0, Math.min(100, props.percentage));
  return circumference.value * (1 - clampedPercentage / 100);
});

const textFontSize = computed(() => {
  if (props.size < 60) return '14px';
  if (props.size < 100) return '18px';
  return '22px';
});
</script>

<style scoped>
.progress-loader-wrapper {
  display: inline-flex;
}

.progress-loader {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--bg-panel);
  box-shadow: var(--shadow-sm);
  padding: 8px;
}

.spinner {
  width: 100%;
  height: 100%;
  transform: rotate(-90deg);
  position: absolute;
  top: 0;
  left: 0;
}

.progress-ring-bg {
  fill: none;
  stroke: var(--border-color);
  stroke-linecap: round;
}

.progress-ring {
  fill: none;
  stroke-linecap: round;
  stroke-dasharray: 283;
  transition: stroke-dashoffset 0.6s cubic-bezier(0.4, 0, 0.2, 1);
  transform-origin: 50% 50%;
  filter: drop-shadow(0 0 4px rgba(59, 130, 246, 0.5));
}

.tech-ring {
  fill: none;
  transform-origin: 50% 50%;
  animation: spin 8s linear infinite;
}

.tech-ring.reverse {
  animation: spin 12s linear infinite reverse;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.progress-content {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.progress-text {
  font-weight: 700;
  font-family: var(--font-mono);
  display: flex;
  align-items: baseline;
  gap: 2px;
}

.percent-sign {
  font-size: 0.6em;
  opacity: 0.7;
}
</style>