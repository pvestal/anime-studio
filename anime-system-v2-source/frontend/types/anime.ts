/**
 * Tower Anime Production System - TypeScript Types
 * For Vue.js frontend integration
 */

// === Enums ===

export enum JobType {
  STILL_IMAGE = 'still_image',
  ANIMATION_LOOP = 'animation_loop',
  FULL_VIDEO = 'full_video',
  CHARACTER_SHEET = 'character_sheet',
}

export enum JobStatus {
  PENDING = 'pending',
  QUEUED = 'queued',
  PROCESSING = 'processing',
  QUALITY_CHECK = 'quality_check',
  COMPLETED = 'completed',
  FAILED = 'failed',
  TIMEOUT = 'timeout',
}

export enum VariationType {
  OUTFIT = 'outfit',
  EXPRESSION = 'expression',
  POSE = 'pose',
  AGE_VARIANT = 'age_variant',
}

export enum Phase {
  PHASE_1_STILL = 'phase_1_still',
  PHASE_2_LOOP = 'phase_2_loop',
  PHASE_3_VIDEO = 'phase_3_video',
}

// === Character Types ===

export interface CharacterAttribute {
  id: string;
  characterId: string;
  attributeType: string;
  attributeValue: string;
  promptTokens: string[];
  priority: number;
  createdAt: string;
}

export interface CharacterAttributeCreate {
  attributeType: string;
  attributeValue: string;
  promptTokens?: string[];
  priority?: number;
}

export interface CharacterVariation {
  id: string;
  characterId: string;
  variationName: string;
  variationType: VariationType;
  promptModifiers: Record<string, unknown>;
  referenceImagePath?: string;
  createdAt: string;
}

export interface CharacterVariationCreate {
  variationName: string;
  variationType: VariationType;
  promptModifiers?: Record<string, unknown>;
  referenceImagePath?: string;
}

export interface CharacterConsistencyUpdate {
  colorPalette?: { primary: string[]; accent: string[] };
  basePrompt?: string;
  negativeTokens?: string[];
  loraModelPath?: string;
}

export interface CharacterEmbeddingRequest {
  referenceImagePath: string;
  forceRecompute?: boolean;
}

export interface CharacterEmbeddingResponse {
  characterId: string;
  embeddingStored: boolean;
  embeddingDimensions: number;
  similarityBaseline?: number;
}

export interface ConsistencyCheckRequest {
  imagePath: string;
  threshold?: number;
}

export interface ConsistencyCheckResponse {
  characterId: string;
  similarityScore: number;
  passesThreshold: boolean;
  thresholdUsed: number;
}

export interface CharacterPromptResponse {
  characterId: string;
  positivePrompt: string;
  negativeTokens: string[];
}

// === Generation Types ===

export interface LoRAConfig {
  name: string;
  path: string;
  weight: number;
}

export interface ControlNetConfig {
  name: string;
  model: string;
  weight: number;
  preprocessor?: string;
}

export interface IPAdapterConfig {
  referenceImagePath: string;
  weight: number;
  noise?: number;
}

export interface GenerateRequest {
  projectId: string;
  characterIds?: string[];
  jobType?: JobType;
  prompt: string;
  negativePrompt?: string;
  width?: number;
  height?: number;
  steps?: number;
  cfgScale?: number;
  seed?: number;
  frameCount?: number;
  fps?: number;
  useCharacterLoras?: boolean;
  useIpadapter?: boolean;
  ipadapterWeight?: number;
  saveParams?: boolean;
  autoQualityCheck?: boolean;
  qualityThresholds?: QualityThresholds;
  poseReferencePath?: string;
  poseWeight?: number;
}

export interface GenerateResponse {
  jobId: string;
  status: JobStatus;
  generationParamsId?: string;
  seedUsed: number;
  estimatedTimeSeconds: number;
  websocketUrl: string;
}

export interface GenerationParams {
  id: string;
  jobId: string;
  positivePrompt: string;
  negativePrompt: string;
  seed: number;
  subseed?: number;
  modelName: string;
  modelHash?: string;
  vaeName?: string;
  samplerName: string;
  scheduler: string;
  steps: number;
  cfgScale: number;
  width: number;
  height: number;
  frameCount: number;
  fps: number;
  loraModels: LoRAConfig[];
  controlnetModels: ControlNetConfig[];
  ipadapterRefs: IPAdapterConfig[];
  createdAt: string;
}

export interface JobProgressResponse {
  jobId: string;
  status: JobStatus;
  progressPercent: number;
  currentStep?: number;
  totalSteps?: number;
  currentFrame?: number;
  totalFrames?: number;
  etaSeconds?: number;
  qualityScores?: QualityScores;
  outputPath?: string;
  errorMessage?: string;
}

export interface ReproduceRequest {
  originalJobId: string;
  modifications?: Record<string, unknown>;
}

// === Quality Types ===

export interface QualityThresholds {
  faceSimilarity?: number;
  aestheticScore?: number;
  temporalLpips?: number;
  motionSmoothness?: number;
  subjectConsistency?: number;
}

export interface QualityScores {
  faceSimilarity?: number;
  aestheticScore?: number;
  temporalLpips?: number;
  motionSmoothness?: number;
  subjectConsistency?: number;
  passesThreshold: boolean;
}

export interface QualityScoresResponse extends QualityScores {
  id: string;
  jobId: string;
  evaluatedAt: string;
}

export interface QualityEvaluationRequest {
  jobId: string;
  outputPath: string;
  characterIds?: string[];
  thresholds?: QualityThresholds;
}

export interface PhaseGateResult {
  phase: Phase;
  passed: boolean;
  testsRun: number;
  testsPassed: number;
  overallScore: number;
  individualResults: TestResult[];
  canAdvance: boolean;
  blockingIssues: string[];
}

export interface TestResult {
  testName: string;
  phase: Phase;
  passed: boolean;
  score?: number;
  threshold?: number;
  durationSeconds: number;
  error?: string;
  details: Record<string, unknown>;
}

// === Story Bible Types ===

export interface StoryBible {
  id: string;
  projectId: string;
  artStyle: string;
  colorPalette: { primary: string[]; accent: string[] };
  lineWeight: string;
  shadingStyle: string;
  settingDescription: string;
  timePeriod: string;
  moodKeywords: string[];
  narrativeThemes: string[];
  globalSeed?: number;
  version: string;
  createdAt: string;
  updatedAt: string;
}

export interface StoryBibleCreate {
  projectId: string;
  artStyle: string;
  colorPalette?: { primary: string[]; accent: string[] };
  lineWeight?: string;
  shadingStyle?: string;
  settingDescription?: string;
  timePeriod?: string;
  moodKeywords?: string[];
  narrativeThemes?: string[];
  globalSeed?: number;
}

export interface StoryBibleUpdate {
  artStyle?: string;
  colorPalette?: { primary: string[]; accent: string[] };
  lineWeight?: string;
  shadingStyle?: string;
  settingDescription?: string;
  timePeriod?: string;
  moodKeywords?: string[];
  narrativeThemes?: string[];
  globalSeed?: number;
}

// === Episode & Scene Types ===

export interface Episode {
  id: string;
  projectId: string;
  episodeNumber: number;
  title: string;
  synopsis: string;
  status: string;
  targetDurationSeconds: number;
  createdAt: string;
}

export interface Scene {
  id: string;
  episodeId: string;
  sceneNumber: number;
  name: string;
  description: string;
  location: string;
  timeOfDay: string;
  mood: string;
  durationFrames: number;
  styleOverrides: Record<string, unknown>;
  createdAt: string;
}

export interface Cut {
  id: string;
  sceneId: string;
  cutNumber: number;
  description: string;
  cameraAngle: string;
  durationFrames: number;
  characterIds: string[];
  dialogue: string;
  actionNotes: string;
  status: string;
  outputPath?: string;
  createdAt: string;
}

// === Echo Brain Types ===

export enum EchoTaskType {
  GENERATE_IMAGE = 'generate_image',
  GENERATE_LOOP = 'generate_loop',
  GENERATE_VIDEO = 'generate_video',
  CHARACTER_DESIGN = 'character_design',
  SCENE_COMPOSITION = 'scene_composition',
  QUALITY_REVIEW = 'quality_review',
  STORY_UPDATE = 'story_update',
}

export interface EchoTaskRequest {
  taskId: string;
  taskType: EchoTaskType;
  projectId: string;
  priority?: number;
  payload: Record<string, unknown>;
  callbackUrl?: string;
  context?: Record<string, unknown>;
}

export interface EchoTaskResponse {
  taskId: string;
  jobId: string;
  status: JobStatus;
  result?: Record<string, unknown>;
  qualityScores?: QualityScores;
  outputPaths: string[];
  error?: string;
}

export interface EchoWebhookPayload {
  eventType: string;
  taskId: string;
  jobId: string;
  timestamp: string;
  data: Record<string, unknown>;
}

// === API Client Interface ===

export interface AnimeApiClient {
  // Health
  health(): Promise<{ status: string; services: Record<string, string> }>;

  // Characters
  storeEmbedding(characterId: string, request: CharacterEmbeddingRequest): Promise<CharacterEmbeddingResponse>;
  checkConsistency(characterId: string, request: ConsistencyCheckRequest): Promise<ConsistencyCheckResponse>;
  updateConsistency(characterId: string, update: CharacterConsistencyUpdate): Promise<{ status: string }>;
  addAttribute(characterId: string, attribute: CharacterAttributeCreate): Promise<CharacterAttribute>;
  getAttributes(characterId: string): Promise<CharacterAttribute[]>;
  createVariation(characterId: string, variation: CharacterVariationCreate): Promise<CharacterVariation>;
  getVariations(characterId: string, type?: VariationType): Promise<CharacterVariation[]>;
  getCharacterPrompt(characterId: string, variationId?: string): Promise<CharacterPromptResponse>;

  // Generation
  generate(request: GenerateRequest): Promise<GenerateResponse>;
  reproduce(jobId: string, request: ReproduceRequest): Promise<GenerateResponse>;
  getParams(jobId: string): Promise<GenerationParams>;
  getProgress(jobId: string): Promise<JobProgressResponse>;

  // Quality
  evaluate(request: QualityEvaluationRequest): Promise<QualityScoresResponse>;
  getQuality(jobId: string): Promise<QualityScoresResponse>;
  evaluatePhaseGate(phase: Phase, jobIds: string[]): Promise<PhaseGateResult>;

  // Story Bible
  createStoryBible(bible: StoryBibleCreate): Promise<StoryBible>;
  getStoryBible(projectId: string): Promise<StoryBible>;
  updateStoryBible(projectId: string, update: StoryBibleUpdate): Promise<StoryBible>;

  // Echo Integration
  handleEchoTask(task: EchoTaskRequest): Promise<EchoTaskResponse>;
}

// === WebSocket Message Types ===

export interface WsProgressMessage {
  type: 'progress';
  jobId: string;
  status: JobStatus;
  progressPercent: number;
  currentStep?: number;
  totalSteps?: number;
  currentFrame?: number;
  totalFrames?: number;
}

export interface WsCompleteMessage {
  type: 'complete';
  jobId: string;
  outputPath: string;
  qualityScores: QualityScores;
}

export interface WsErrorMessage {
  type: 'error';
  jobId: string;
  error: string;
}

export type WsMessage = WsProgressMessage | WsCompleteMessage | WsErrorMessage;
