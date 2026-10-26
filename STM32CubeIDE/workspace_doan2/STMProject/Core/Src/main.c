/**
 * Smart Parking prototype: STM32F407VG + MFRC522 + LCD1602 + UART.
 * PC performs recognition/storage; this firmware reads UID and signals results.
 */
#include "main.h"
#include "gpio.h"
#include "i2c.h"
#include "spi.h"
#include "usart.h"
/* USER CODE BEGIN Includes */
#include "RC522.h"
#include "liquidcrystal_i2c.h"
#include <stdio.h>
#include <string.h>

/* USER CODE END Includes */

/* USER CODE BEGIN PD */
#define RX_BUFFER_SIZE 128U
#define COMMAND_QUEUE_SIZE 8U
#define USER_BTN_Pin GPIO_PIN_0
#define USER_BTN_GPIO_Port GPIOA

/* USER CODE END PD */

/* USER CODE BEGIN PV */
static uint8_t rx_byte;
static char rx_buffer[RX_BUFFER_SIZE];
static uint16_t rx_index;
static uint8_t rx_discard;
static char command_queue[COMMAND_QUEUE_SIZE][RX_BUFFER_SIZE];
static volatile uint8_t queue_head;
static volatile uint8_t queue_tail;
static volatile uint8_t queue_overflow;
static uint8_t parking_mode;
static uint8_t transaction_active;
static uint8_t signal_active;
static uint32_t signal_until;
static uint32_t buzzer_until;
static char current_plate[17];

/* USER CODE END PV */

void SystemClock_Config(void);

/* USER CODE BEGIN 0 */
static void LCD_Message(const char *first, const char *second) {
    char line[17];
    HD44780_Clear();
    HD44780_SetCursor(0, 0);
    snprintf(line, sizeof(line), "%.16s", first);
    HD44780_PrintStr(line);
    HD44780_SetCursor(0, 1);
    snprintf(line, sizeof(line), "%.16s", second);
    HD44780_PrintStr(line);
}

static void LCD_ShowIdle(void) {
    LCD_Message(parking_mode ? "CHE DO: LAY XE" : "CHE DO: GUI XE", "Moi quet the...");
}

static void Reset_Transaction(void) {
    transaction_active = 0;
    signal_active = 0;
    current_plate[0] = '\0';
    HAL_GPIO_WritePin(GPIOD, YELLOW_LED_Pin | RED_LED_Pin | BUZZER_Pin, GPIO_PIN_RESET);
    LCD_ShowIdle();
}

static void Process_PC_Command(const char *cmd) {
    if (strcmp(cmd, "CMD:RESET") == 0) {
        Reset_Transaction();
    } else if (strcmp(cmd, "CMD:SCAN_PLATE") == 0) {
        signal_active = 0;
        HAL_GPIO_WritePin(GPIOD, YELLOW_LED_Pin | RED_LED_Pin | BUZZER_Pin, GPIO_PIN_RESET);
        transaction_active = 1;
        current_plate[0] = '\0';
        LCD_Message("Dang quet BS...", "");
    } else if (strncmp(cmd, "CMD:PLATE:", 10) == 0) {
        snprintf(current_plate, sizeof(current_plate), "%.16s", cmd + 10);
        LCD_Message("Bien so:", current_plate);
    } else if (strcmp(cmd, "CMD:SCAN_FACE") == 0) {
        LCD_Message(current_plate, "Dang quet mat...");
    } else if (strcmp(cmd, "CMD:MASK_WARN") == 0) {
        LCD_Message(current_plate, "Thao khau trang!");
    } else if (strcmp(cmd, "CMD:FACE_OK") == 0) {
        LCD_Message(current_plate, "Da nhan dien mat");
    } else if (strcmp(cmd, "CMD:SUCCESS") == 0) {
        transaction_active = 0;
        signal_active = 1;
        signal_until = HAL_GetTick() + 3000;
        HAL_GPIO_WritePin(YELLOW_LED_GPIO_Port, YELLOW_LED_Pin, GPIO_PIN_SET);
        HAL_GPIO_WritePin(RED_LED_GPIO_Port, RED_LED_Pin, GPIO_PIN_RESET);
        HAL_GPIO_WritePin(BUZZER_GPIO_Port, BUZZER_Pin, GPIO_PIN_RESET);
        LCD_Message(parking_mode ? "HEN GAP LAI" : "WELCOME!", "");
    } else if (strncmp(cmd, "CMD:ERROR:", 10) == 0) {
        signal_active = 1;
        signal_until = HAL_GetTick() + 3000;
        buzzer_until = HAL_GetTick() + 500;
        HAL_GPIO_WritePin(YELLOW_LED_GPIO_Port, YELLOW_LED_Pin, GPIO_PIN_RESET);
        HAL_GPIO_WritePin(RED_LED_GPIO_Port, RED_LED_Pin, GPIO_PIN_SET);
        HAL_GPIO_WritePin(BUZZER_GPIO_Port, BUZZER_Pin, GPIO_PIN_SET);
        LCD_Message("LOI XAY RA!", cmd + 10);
    }
}

/* The IRQ owns rx_buffer. Completed lines are copied to a bounded FIFO so
 * receiving the next line cannot overwrite a command being processed by main.
 * Oversized lines are discarded completely, including their truncated tail.
 */
void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart) {
    if (huart->Instance != USART2) return;
    if (rx_byte == '\n' || rx_byte == '\r') {
        if (rx_index && !rx_discard) {
            uint8_t next = (uint8_t)((queue_head + 1U) % COMMAND_QUEUE_SIZE);
            rx_buffer[rx_index] = '\0';
            if (next != queue_tail) {
                memcpy(command_queue[queue_head], rx_buffer, rx_index + 1U);
                __DMB();
                queue_head = next;
            } else {
                queue_overflow = 1;
            }
        }
        rx_index = 0;
        rx_discard = 0;
    } else if (!rx_discard) {
        if (rx_index < RX_BUFFER_SIZE - 1U) rx_buffer[rx_index++] = (char)rx_byte;
        else rx_discard = 1;
    }
    HAL_UART_Receive_IT(&huart2, &rx_byte, 1);
}

/* USER CODE END 0 */

int main(void) {
    HAL_Init();
    SystemClock_Config();
    MX_GPIO_Init();
    MX_SPI1_Init();

    MX_USART2_UART_Init();
    MX_I2C1_Init();

    /* USER CODE BEGIN 2 */
    /* Deselect the Discovery board accelerometer sharing SPI1. */
    __HAL_RCC_GPIOE_CLK_ENABLE();
    GPIO_InitTypeDef gpio = {0};
    gpio.Pin = GPIO_PIN_3;
    gpio.Mode = GPIO_MODE_OUTPUT_PP;
    gpio.Pull = GPIO_NOPULL;
    gpio.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(GPIOE, &gpio);
    HAL_GPIO_WritePin(GPIOE, GPIO_PIN_3, GPIO_PIN_SET);

    MFRC522_Init();
    HD44780_Init(2);
    HD44780_Backlight();
    LCD_ShowIdle();
    HAL_UART_Receive_IT(&huart2, &rx_byte, 1);

    uint8_t last_button = 0;
    uint8_t stable_button = 0;
    uint32_t button_changed = HAL_GetTick();
    uint32_t last_rfid_poll = 0;
    char command[RX_BUFFER_SIZE];

    /* USER CODE END 2 */

    /* USER CODE BEGIN WHILE */
    while (1) {
        /* USER CODE END WHILE */
        /* USER CODE BEGIN 3 */
        /* Interrupts stay enabled: the IRQ never writes the slot at tail until
         * main advances tail, so copying a completed command is safe here.
         */
        if (queue_tail != queue_head) {
            __DMB();
            memcpy(command, command_queue[queue_tail], sizeof(command));
            __DMB();
            queue_tail = (uint8_t)((queue_tail + 1U) % COMMAND_QUEUE_SIZE);
            Process_PC_Command(command);
        }
        if (queue_overflow) {
            queue_overflow = 0;
            const char warning[] = "WARN:UART_QUEUE_FULL\n";
            HAL_UART_Transmit(&huart2, (uint8_t *)warning, sizeof(warning) - 1U, 100);
        }

        uint32_t now = HAL_GetTick();
        if ((int32_t)(now - buzzer_until) >= 0)
            HAL_GPIO_WritePin(BUZZER_GPIO_Port, BUZZER_Pin, GPIO_PIN_RESET);
        if (signal_active && (int32_t)(now - signal_until) >= 0) {
            signal_active = 0;
            HAL_GPIO_WritePin(GPIOD, YELLOW_LED_Pin | RED_LED_Pin, GPIO_PIN_RESET);
            if (transaction_active) LCD_Message(current_plate, "Quet lai / Reset");
            else LCD_ShowIdle();
        }

        /* Debounced rising edge: holding PA0 cannot repeatedly toggle mode. */
        uint8_t button = HAL_GPIO_ReadPin(USER_BTN_GPIO_Port, USER_BTN_Pin) == GPIO_PIN_SET;
        if (button != last_button) { last_button = button; button_changed = now; }
        if (button != stable_button && now - button_changed >= 50U) {
            stable_button = button;
            if (button && !transaction_active && !signal_active) {
                parking_mode = !parking_mode;
                LCD_ShowIdle();
                const char *mode = parking_mode ? "MODE:OUT\n" : "MODE:IN\n";
                HAL_UART_Transmit(&huart2, (uint8_t *)mode, strlen(mode), 100);
            }
        }

        if (!transaction_active && !signal_active && now - last_rfid_poll >= 50U) {
            last_rfid_poll = now;
            uint8_t uid[MAX_LEN];
            if (MFRC522_Request(PICC_REQIDL, uid) == MI_OK && MFRC522_Anticoll(uid) == MI_OK) {
                char uid_line[17], message[64];
                snprintf(uid_line, sizeof(uid_line), "UID: %02X%02X%02X%02X", uid[0], uid[1], uid[2], uid[3]);
                LCD_Message("Quet thanh cong!", uid_line);
                snprintf(message, sizeof(message), "UID:%02X%02X%02X%02X|MODE:%s\n",
                         uid[0], uid[1], uid[2], uid[3], parking_mode ? "OUT" : "IN");
                HAL_UART_Transmit(&huart2, (uint8_t *)message, strlen(message), 100);
                HAL_GPIO_WritePin(BUZZER_GPIO_Port, BUZZER_Pin, GPIO_PIN_SET);
                buzzer_until = HAL_GetTick() + 100;
                MFRC522_Halt();
            }
        }
    }
    /* USER CODE END 3 */
}

void Error_Handler(void) {
    __disable_irq();
    while (1) {}
}

void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Configure the main internal regulator output voltage
  */
  __HAL_RCC_PWR_CLK_ENABLE();
  __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE1);

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLM = 8;
  RCC_OscInitStruct.PLL.PLLN = 336;
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV2;
  RCC_OscInitStruct.PLL.PLLQ = 7;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses Clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV4;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV2;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_5) != HAL_OK)
  {
    Error_Handler();
  }
}
/* USER CODE END 4 */
