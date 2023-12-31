package ca.petsearch.controllers;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HealthController {

    Logger logger = LoggerFactory.getLogger(HealthController.class);

    @GetMapping("/health/status")
    public String status(){
        logger.info("Testing");
        return "Alive";
    }
}
